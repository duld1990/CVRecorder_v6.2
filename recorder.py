"""Four-channel USB recorder with independent capture settings and persistent preview."""
import csv
import hashlib
import io
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import queue
import re
import shutil
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


CHANNELS = 4


def parse_capture(resolution, fps, input_format):
    parts = resolution.lower().replace(" ", "").split("x")
    if len(parts) != 2:
        raise ValueError("Resolution must be WIDTHxHEIGHT, e.g. 1280x720.")
    width, height = (int(x) for x in parts)
    fps = float(fps)
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError("Width and Height must be positive even integers.")
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("FPS must be a positive finite number.")
    if input_format not in ("AUTO", "MJPG", "YUY2"):
        raise ValueError("Input format must be AUTO, MJPG, or YUY2.")
    return dict(width=width, height=height, fps=fps, input_format=input_format)


def fourcc_text(value):
    if not math.isfinite(value) or value <= 0:
        return "unknown"
    n = int(value)
    text = "".join(chr((n >> (8*i)) & 255) for i in range(4))
    return text if all(32 <= ord(c) < 127 for c in text) else "unknown"


def safe_token(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value.strip()).strip(' .')
    return value[:48]


def file_stem(slot, camera, animal):
    camera = safe_token(camera) or str(slot+1)
    animal = safe_token(animal)
    return f'Camera{camera}' + (f'_ID{animal}' if animal else '') + f'_slot{slot+1}'


def source_label(d):
    name = 'Index '+str(d['index']) if d.get('manual') else d['name']
    if re.search(r'C920',name,re.I):name='C920'
    name=' '.join(name.split())
    name=name if len(name)<=20 else name[:17]+'...'
    virtual=any(x in d['name'].lower() for x in ['obs','virtual','manycam','snap camera'])
    status=d.get('availability','UNCHECKED')
    return f"{d['index']} | {name}{' [VIRTUAL?]' if virtual else ''} | {status}"


def probe_source(source, output):
    cap=None;cleanup=lambda:None
    try:
        cleanup=com_context(source['backend'])
        import cv2
        cap=cv2.VideoCapture(source['index'],source['backend'])
        if not cap.isOpened():
            output.put(('probe','UNAVAILABLE'));return
        for _ in range(3):
            ok,frame=cap.read()
            if ok and frame is not None:
                output.put(('probe','READY'));return
        output.put(('probe','NO FRAME'))
    except Exception as exc:
        output.put(('probe','UNAVAILABLE',str(exc)))
    finally:
        if cap is not None:cap.release()
        cleanup()


def com_context(backend):
    """Windows subprocesses need their own COM initialization."""
    if os.name != 'nt':
        return lambda: None
    import ctypes
    ole32 = ctypes.WinDLL('ole32')
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.restype = None
    hr = ole32.CoInitializeEx(None, 2 if backend == 700 else 0)
    return ole32.CoUninitialize if hr in (0, 1) else (lambda: None)


def index_sources(backend_name, named=()):
    """Candidates are not claimed to be connected or verified devices."""
    backend = {'DSHOW':700, 'MSMF':1400}[backend_name]
    result = list(named)
    known = {d['index'] for d in result}
    for index in range(16):
        if index not in known:
            result.append(dict(index=index, backend=backend, backend_name=backend_name,
                               name='UNVERIFIED index / name unavailable',path='',vid=None,pid=None,manual=True))
    return result


def enumerate_worker(backend, output):
    cleanup = lambda: None
    try:
        cleanup = com_context({'DSHOW':700,'MSMF':1400}[backend])
        from cv2_enumerate_cameras import enumerate_cameras
        devices = [dict(index=int(c.index), backend=int(c.backend), name=c.name,
                        path=c.path or '', vid=c.vid, pid=c.pid, backend_name=backend)
                   for c in enumerate_cameras({'DSHOW':700,'MSMF':1400}[backend])]
        output.put(('devices', devices))
    except Exception as exc:
        output.put(('error', type(exc).__name__+': '+str(exc)))
    finally:
        cleanup()


def camera_worker(slot, source, capture, commands, events, images, quit_event, gate, epoch):
    import cv2
    cv2.setNumThreads(1)
    # Do not let an unread preview queue block process shutdown.
    images.cancel_join_thread()
    cap = writer = log = None
    job = None
    armed = recording = False
    count = failures = 0
    first = last = None
    error = None
    cleanup = lambda: None
    def report(kind, **kw):
        events.put(dict(slot=slot, kind=kind, connection=source.get('connection',0), **kw))
    def finish(reason):
        nonlocal writer, log, job, armed, recording
        if writer is not None:
            writer.release()
            writer = None
        if log is not None:
            log.close()
            log = None
        if job is not None:
            summary = dict(source=source, capture=capture, actual=actual,
                           camera=job['camera'], animal_id=job['animal'], stem=job['stem'],
                           frames=count, read_failures=failures, reason=reason,
                           first_host_monotonic=first, last_host_monotonic=last,
                           measured_fps=(count-1)/(last-first) if count>1 and last>first else None)
            Path(job['folder'],job['stem']+'_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
            report('record_done',reason=reason,frames=count)
        job = None
        armed = recording = False
    try:
        cleanup = com_context(source['backend'])
        # Enumeration is repeated to detect stale index/path pairs before opening.
        if source['path']:
            from cv2_enumerate_cameras import enumerate_cameras
            current = list(enumerate_cameras(source['backend']))
            if not any(c.index==source['index'] and c.path==source['path'] for c in current):
                raise RuntimeError('Device identity changed. Disconnect previews and refresh sources.')
        cap = cv2.VideoCapture(source['index'],source['backend'])
        if not cap.isOpened():
            raise RuntimeError('Cannot open source. Close other camera apps and check USB connection.')
        set_results = {}
        for name, prop in [('width',cv2.CAP_PROP_FRAME_WIDTH), ('height',cv2.CAP_PROP_FRAME_HEIGHT), ('fps',cv2.CAP_PROP_FPS)]:
            set_results[name] = bool(cap.set(prop,capture[name]))
        if capture['input_format'] != 'AUTO':
            set_results['input_format'] = bool(cap.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*capture['input_format'])))
        actual = {}
        last_preview = last_status = 0
        received = rate_count = 0
        rate_time = time.perf_counter()
        consecutive = 0
        segment = -1
        local = 0
        while not quit_event.is_set():
            while True:
                try:
                    command = commands.get_nowait()
                except queue.Empty:
                    break
                if command['action']=='prepare':
                    if job is not None:
                        raise RuntimeError('A recording job is already active.')
                    job = command['job']
                    count = failures = 0
                    first = last = None
                    segment = -1
                    # Open the encoder before releasing the shared start gate.
                    ext, codec = ('.mp4','mp4v') if job['format']=='MP4' else ('.avi','MJPG')
                    stem = Path(job['folder'],job['stem']+'_part0001')
                    writer = cv2.VideoWriter(str(stem)+ext,cv2.VideoWriter_fourcc(*codec),capture['fps'],(w,h))
                    if not writer.isOpened():
                        raise RuntimeError('Cannot create output video with '+codec)
                    log = open(str(stem)+'_timestamps.csv','w',newline='',buffering=1)
                    rows = csv.writer(log)
                    rows.writerow(['frame_in_segment','frame_total','host_unix_ns','host_monotonic_ns','session_seconds'])
                    segment = local = 0
                    armed = True
                    report('armed')
                elif command['action']=='stop':
                    finish('stopped by user')
            ok, frame = cap.read()
            now, wall = time.perf_counter(), time.time_ns()
            if not ok:
                consecutive += 1
                if job: failures += 1
                if consecutive==1: report('signal_lost')
                if consecutive>=30: raise RuntimeError('30 consecutive capture read failures.')
                time.sleep(.01)
                continue
            if consecutive: report('signal_restored')
            consecutive = 0
            if not actual:
                h,w = frame.shape[:2]
                actual = dict(width=w,height=h,reported_fps=cap.get(cv2.CAP_PROP_FPS),input_fourcc=fourcc_text(cap.get(cv2.CAP_PROP_FOURCC)),set_results=set_results)
                report('connected',actual=actual)
                if (w,h)!=(capture['width'],capture['height']):
                    report('warning',message=f'Requested {capture["width"]}x{capture["height"]}, received {w}x{h}. Driver substituted resolution.')
                if actual['reported_fps']>0 and abs(actual['reported_fps']-capture['fps'])>max(.5,capture['fps']*.02):
                    report('warning',message=f'Requested {capture["fps"]} FPS; driver reports {actual["reported_fps"]}. Check measured FPS.')
                if capture['input_format']!='AUTO' and actual['input_fourcc'] not in ('unknown',capture['input_format']):
                    report('warning',message=f'Requested input {capture["input_format"]}; driver reports {actual["input_fourcc"]}.')
                if any(not accepted for accepted in set_results.values()):
                    report('warning',message='Driver rejected one or more requested settings. Inspect actual mode and measured FPS.')
            elif frame.shape[:2]!=(h,w):
                raise RuntimeError('Camera resolution changed. Reconnect preview.')
            received += 1
            if armed and gate.is_set() and now>=epoch.value:
                armed = False
                recording = True
            if recording:
                elapsed = now-epoch.value
                if elapsed>=job['minutes']*60:
                    finish('duration reached')
                else:
                    seg = int(elapsed//(job['segment']*60))
                    if seg!=segment:
                        writer.release(); log.close()
                        segment, local = seg, 0
                        stem = Path(job['folder'],job['stem']+f'_part{seg+1:04d}')
                        writer = cv2.VideoWriter(str(stem)+ext,cv2.VideoWriter_fourcc(*codec),capture['fps'],(w,h))
                        if not writer.isOpened(): raise RuntimeError('Cannot open next video segment.')
                        log = open(str(stem)+'_timestamps.csv','w',newline='',buffering=1)
                        rows = csv.writer(log)
                        rows.writerow(['frame_in_segment','frame_total','host_unix_ns','host_monotonic_ns','session_seconds'])
                    writer.write(frame)
                    rows.writerow([local,count,wall,int(now*1e9),f'{elapsed:.9f}'])
                    local += 1; count += 1
                    first = now if first is None else first
                    last = now
            if now-last_preview>=.2:
                # Preserve aspect ratio in the GUI. Raw saved frames are unchanged.
                scale = min(320/w,180/h)
                thumb = cv2.resize(frame,(max(1,int(w*scale)),max(1,int(h*scale))))
                ok_j,jpg = cv2.imencode('.jpg',thumb,[cv2.IMWRITE_JPEG_QUALITY,75])
                if ok_j:
                    try: images.put_nowait((now,jpg.tobytes()))
                    except queue.Full: pass
                last_preview = now
            if now-last_status>=1:
                fps = (count-1)/(last-first) if count>1 and last>first else 0
                live_fps = (received-rate_count)/max(now-rate_time,.001)
                rate_count, rate_time = received, now
                report('status',recording=recording,frames=count,fps=round(fps,2),live_fps=round(live_fps,2),actual=actual,elapsed=round(now-epoch.value,1) if recording else 0)
                last_status = now
    except Exception as exc:
        error = str(exc)
        report('error',message=error)
    finally:
        try: finish(error or 'source disconnected')
        except Exception as exc: report('error',message='Finalization failed: '+str(exc))
        if cap is not None: cap.release()
        cleanup()
        report('closed')


class App:
    def __init__(self,root):
        self.root=root; root.title('Four-channel Webcam Recorder v6.2 | Four channels')
        root.geometry(f'{min(1100,root.winfo_screenwidth()-50)}x{min(950,root.winfo_screenheight()-80)}')
        self.ctx=mp.get_context('spawn'); self.events=self.ctx.Queue()
        self.gate=self.ctx.Event(); self.epoch=self.ctx.Value('d',0)
        self.devices={}; self.slots=[None]*CHANNELS; self.pending={}; self.photos=[None]*CHANNELS
        self.live=[0]*CHANNELS; self.armed=set(); self.done=set(); self.running=False
        self.stopping=False; self.closing=False; self.scan_process=None
        self.folder=None; self.active=set()
        toolbar=ttk.Frame(root,padding=6);toolbar.pack(fill='x')
        self.toolbar=toolbar
        self.scan_status=tk.StringVar(value='Index list available. Reading camera names on startup...')
        ttk.Label(root,textvariable=self.scan_status,wraplength=1000,foreground='#993300').pack(fill='x',padx=8)
        outer=ttk.Frame(root);outer.pack(fill='both',expand=True)
        canvas=tk.Canvas(outer,highlightthickness=0)
        bar=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        top=ttk.Frame(canvas,padding=10);window=canvas.create_window((0,0),window=top,anchor='nw')
        top.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(window,width=max(e.width,820)))
        def wheel(e):
            if e.widget.winfo_class() not in ('TCombobox','Text'):
                canvas.yview_scroll(-int(e.delta/120),'units')
        root.bind_all('<MouseWheel>',wheel)
        self.vars={}
        for col,(key,value) in enumerate([('Minutes','60'),('Segment minutes','10')]):
            cell=ttk.Frame(top);cell.grid(row=0,column=col,sticky='w',padx=4)
            ttk.Label(cell,text=key).pack(anchor='w')
            v=self.vars[key]=tk.StringVar(value=value)
            ttk.Entry(cell,textvariable=v,width=12).pack()
        self.backend=tk.StringVar(value='DSHOW'); self.format=tk.StringVar(value='MP4')
        ttk.Combobox(top,textvariable=self.backend,values=['DSHOW','MSMF'],state='readonly',width=10).grid(row=0,column=5)
        ttk.Combobox(top,textvariable=self.format,values=['MP4','AVI'],state='readonly',width=8).grid(row=0,column=6)
        self.output=tk.StringVar(value=str(Path.home()/'Videos'/'Behavior'))
        ttk.Label(top,text='Output folder').grid(row=1,column=0,sticky='w',pady=8)
        ttk.Entry(top,textvariable=self.output,width=80).grid(row=1,column=1,columnspan=5,sticky='ew')
        ttk.Button(top,text='Browse',command=self.browse).grid(row=1,column=6)
        self.source_vars=[]; self.boxes=[]; self.labels=[]; self.status=[]; self.identities=[];self.badges=[]
        self.camera_vars=[];self.id_vars=[];self.filenames=[];self.naming_entries=[]
        self.capture_vars=[];self.capture_boxes=[];self.apply_buttons=[]
        cams=ttk.Frame(top);cams.grid(row=2,column=0,columnspan=7)
        for i in range(CHANNELS):
            f=ttk.LabelFrame(cams,text=f'Recording slot {i+1}',padding=6);f.grid(row=i//2,column=i%2,padx=5,pady=5,sticky='n')
            ttk.Label(f,text='Source: index | camera | check result').pack(anchor='w')
            var=tk.StringVar(value='');self.source_vars.append(var)
            box=ttk.Combobox(f,textvariable=var,values=[''],width=48,state='readonly');box.pack(fill='x')
            box.bind('<<ComboboxSelected>>',lambda e,j=i:self.select(j));self.boxes.append(box)
            badge=ttk.Label(f,text='NOT SELECTED',foreground='#666666');badge.pack(anchor='w');self.badges.append(badge)
            identity=ttk.Label(f,text='No source selected',wraplength=390);identity.pack(fill='x');self.identities.append(identity)
            ttk.Button(f,text='Details',command=lambda j=i:self.device_details(j)).pack(anchor='w')
            controls=ttk.Frame(f);controls.pack(fill='x',pady=4)
            capture_vars={}
            for title,default,choices in [('Resolution','1280x720',['640x480','800x600','1280x720','1920x1080']),('FPS','30',['5','10','15','20','25','30','60']),('Input','MJPG',['AUTO','MJPG','YUY2'])]:
                cell=ttk.Frame(controls);cell.pack(side='left',padx=3)
                ttk.Label(cell,text=title).pack(anchor='w')
                var=tk.StringVar(value=default);capture_vars[title]=var
                box=ttk.Combobox(cell,textvariable=var,values=choices,width=12 if title=='Resolution' else 7,state='readonly' if title=='Input' else 'normal');box.pack()
                self.capture_boxes.append((box,title))
            self.capture_vars.append(capture_vars)
            apply_btn=ttk.Button(f,text='Apply',command=lambda j=i:self.select(j));apply_btn.pack(fill='x');self.apply_buttons.append(apply_btn)
            view=tk.Frame(f,width=320,height=180,bg='black');view.pack(pady=5);view.pack_propagate(False)
            label=tk.Label(view,text='NO SIGNAL',bg='black',fg='#ff6868',font=('Arial',24,'bold'));label.pack(fill='both',expand=True);self.labels.append(label)
            status=ttk.Label(f,text='Select a source to start LIVE PREVIEW.',wraplength=390);status.pack(fill='x');self.status.append(status)
            row=ttk.Frame(f);row.pack(fill='x',pady=6)
            cv=tk.StringVar();iv=tk.StringVar();self.camera_vars.append(cv);self.id_vars.append(iv)
            for name,v in [('Camera#',cv),('ID#',iv)]:
                ttk.Label(row,text=name).pack(side='left');e=ttk.Entry(row,textvariable=v,width=12);e.pack(side='left',padx=4);self.naming_entries.append(e)
                v.trace_add('write',lambda *a,j=i:self.update_name(j))
            fn=ttk.Label(f,text='',wraplength=390);fn.pack(fill='x');self.filenames.append(fn);self.update_name(i)
        self.format.trace_add('write',lambda *a:[self.update_name(j) for j in range(CHANNELS)])
        actions=self.toolbar
        self.scan_btn=ttk.Button(actions,text='Refresh',command=self.scan);self.scan_btn.grid(row=0,column=0,padx=4,pady=2,sticky='w')
        self.manual_btn=ttk.Button(actions,text='Index list',command=self.manual_sources);self.manual_btn.grid(row=0,column=1,padx=4,pady=2,sticky='w')
        self.disconnect_btn=ttk.Button(actions,text='Disconnect',command=self.disconnect);self.disconnect_btn.grid(row=0,column=2,padx=4,pady=2,sticky='w')
        self.start_btn=ttk.Button(actions,text='Start',command=self.start);self.start_btn.grid(row=1,column=0,padx=4,pady=2,sticky='w')
        self.stop_btn=ttk.Button(actions,text='Stop',command=self.stop,state='disabled');self.stop_btn.grid(row=1,column=1,padx=4,pady=2,sticky='w')
        self.info=ttk.Label(top,text='Preview only until Start recording. For identical cameras, cover one lens to identify its live view.');self.info.grid(row=4,column=0,columnspan=7,sticky='w')
        self.log=tk.Text(top,height=5,width=100,state='disabled');self.log.grid(row=5,column=0,columnspan=7)
        self.install_sources(index_sources(self.backend.get()))
        root.protocol('WM_DELETE_WINDOW',self.close);root.after(100,self.poll);root.after(300,self.scan)
    def note(self,text):
        self.log.configure(state='normal');self.log.insert('end',time.strftime('%H:%M:%S')+' '+text+'\n');self.log.see('end');self.log.configure(state='disabled')
        if 'ERROR' in text or 'failed' in text.lower():
            self.scan_status.set(text)
    def no_signal(self,i,text):
        self.photos[i]=None;self.labels[i].configure(image='',text='NO SIGNAL');self.status[i].configure(text=text);self.live[i]=0
        self.badges[i].configure(text='NOT SELECTED' if not self.source_vars[i].get() else 'NO SIGNAL',foreground='#bb3333')
    def update_name(self,i):
        self.filenames[i].configure(text='Filename: '+file_stem(i,self.camera_vars[i].get(),self.id_vars[i].get())+'_part0001'+('.mp4' if self.format.get()=='MP4' else '.avi'))
    def browse(self):
        p=filedialog.askdirectory()
        if p:self.output.set(p)
    def device_details(self,i):
        source=self.devices.get(self.source_vars[i].get())
        if source:
            messagebox.showinfo('Device details',json.dumps(source,indent=2,ensure_ascii=False))
    def capture_settings(self,i):
        v=self.capture_vars[i]
        return parse_capture(v['Resolution'].get(),v['FPS'].get(),v['Input'].get())
    def install_sources(self,devices):
        self.devices={source_label(d):d for d in devices}
        for b in self.boxes:b.configure(values=['']+list(self.devices))
    def cancel_scan(self):
        if self.scan_process:
            self.scan_process.join(.15)
            if self.scan_process.is_alive():self.scan_process.terminate()
            self.scan_process.join(.2);self.scan_process=None;self.scan_q.close()
            self.scan_btn.configure(state='normal')
    def manual_sources(self):
        if self.running:return
        if any(self.slots):
            self.scan_status.set('Disconnect previews before switching the source list.');return
        self.cancel_scan()
        for v in self.source_vars:v.set('')
        self.install_sources(index_sources(self.backend.get()))
        self.scan_status.set('Index list: 0-15 are UNVERIFIED candidates, not detected cameras. Select one and verify its preview.')
        self.note('Using index fallback. Check the live image to identify the physical camera or virtual source.')
    def scan(self):
        if self.running or self.scan_process:return
        if any(self.slots):
            self.scan_status.set('Disconnect previews before refreshing sources.');return
        for v in self.source_vars:v.set('')
        self.scan_backend=self.backend.get()
        self.install_sources(index_sources(self.scan_backend))
        self.scan_status.set('Scanning '+self.scan_backend+' names... Index fallback remains available; selecting a candidate cancels the name scan.')
        self.scan_q=self.ctx.Queue();self.scan_process=self.ctx.Process(target=enumerate_worker,args=(self.scan_backend,self.scan_q))
        self.scan_stage='names'
        self.scan_process.start();self.scan_time=time.perf_counter()
        self.scan_btn.configure(state='disabled');self.note('Reading device names and paths...')
    def next_probe(self):
        if self.check_index>=len(self.checked_devices):
            ready=sum(d.get('availability')=='READY' for d in self.checked_devices)
            self.scan_status.set(f'{len(self.checked_devices)} detected, {ready} readable at scan time. READY is a scan result; verify selected settings in live preview.')
            self.scan_btn.configure(state='normal')
            self.note('Source checks completed. READY means a frame was read, not guaranteed long-term stability.')
            return
        device=self.checked_devices[self.check_index]
        self.scan_q=self.ctx.Queue();self.scan_process=self.ctx.Process(target=probe_source,args=(device,self.scan_q))
        self.scan_stage='probe';self.scan_time=time.perf_counter();self.scan_process.start()
        self.scan_btn.configure(state='disabled')
        self.scan_status.set(f'Checking {self.check_index+1}/{len(self.checked_devices)}: {device["name"][:36]}...')
    def select(self,i):
        if self.running:return
        if self.scan_process:
            self.cancel_scan()
            self.scan_status.set('Name scan cancelled. Using unverified index selection; inspect the live preview.')
        label=self.source_vars[i].get();source=self.devices.get(label)
        if source:
            key=(source['backend'],source['index'])
            for j,v in enumerate(self.source_vars):
                other=self.devices.get(v.get())
                if j!=i and other and (other['backend'],other['index'])==key:
                    self.source_vars[i].set('');source=None;self.note('This source is already selected in another slot.');break
        self.pending[i]=source
        old=self.slots[i]
        if old:old['quit'].set();old['disconnect_time']=time.perf_counter()
        else:self.open_pending(i)
    def open_pending(self,i):
        source=self.pending.pop(i,None)
        self.no_signal(i,'No source selected' if source is None else 'Connecting for live preview...')
        if source is None:self.identities[i].configure(text='No source selected');return
        try:
            capture=self.capture_settings(i)
            source=dict(source,connection=time.time_ns())
            self.badges[i].configure(text='CONNECTING',foreground='#996600')
            self.identities[i].configure(text=source['backend_name']+' | '+('Name unavailable' if source.get('manual') else source['name'][:36]))
            self.note(f"Slot {i+1}: {source_label(source)}")
            if source.get('manual'):
                self.scan_status.set(f'Channel {i+1}: unverified index {source["index"]}. Confirm the physical camera using preview; names/virtual-device warnings are unavailable.')
            if '[VIRTUAL?]' in source_label(source):self.note('WARNING: likely virtual source. Verify the live image before recording.')
            cmd=self.ctx.Queue();images=self.ctx.Queue(maxsize=1);quit_event=self.ctx.Event()
            p=self.ctx.Process(target=camera_worker,args=(i,source,capture,cmd,self.events,images,quit_event,self.gate,self.epoch))
            p.start();self.slots[i]=dict(process=p,cmd=cmd,images=images,quit=quit_event,source=source,capture=capture,opened=time.perf_counter(),healthy=False)
        except Exception as exc:self.no_signal(i,str(exc));self.note(str(exc))
    def disconnect(self):
        if self.running:return
        for i,s in enumerate(self.slots):
            self.source_vars[i].set('');self.pending[i]=None
            if s:s['quit'].set();s['disconnect_time']=time.perf_counter()
            else:self.open_pending(i)
    def locked(self,yes):
        for b in self.boxes:b.configure(state='disabled' if yes else 'readonly')
        for e in self.naming_entries:e.configure(state='disabled' if yes else 'normal')
        for box,title in self.capture_boxes:box.configure(state='disabled' if yes else ('readonly' if title=='Input' else 'normal'))
        for b in self.apply_buttons:b.configure(state='disabled' if yes else 'normal')
        for b in [self.start_btn,self.scan_btn,self.manual_btn,self.disconnect_btn]:b.configure(state='disabled' if yes else 'normal')
        self.stop_btn.configure(state='normal' if yes else 'disabled')
    def start(self):
        if self.running:return
        try:
            if self.scan_process or self.pending:raise ValueError('Wait for source connection to finish.')
            self.active={i for i,v in enumerate(self.source_vars) if v.get().strip()}
            if not self.active:raise ValueError('Select at least one source. Up to four channels can record together.')
            for i in self.active:
                s=self.slots[i]
                if not s or not s['process'].is_alive() or not s['healthy'] or time.perf_counter()-self.live[i]>2:
                    raise ValueError(f'Channel {i+1} needs a fresh live preview before recording.')
                if self.capture_settings(i)!=s['capture']:
                    raise ValueError(f'Channel {i+1} settings changed. Click Apply parameters and verify preview first.')
            minutes=float(self.vars['Minutes'].get());segment=float(self.vars['Segment minutes'].get())
            if not all(math.isfinite(x) and x>0 for x in [minutes,segment]):raise ValueError('Duration and segment length must be positive finite numbers.')
            folder=Path(self.output.get()).expanduser();folder.mkdir(parents=True,exist_ok=True)
            if shutil.disk_usage(folder).free<5*1024**3:raise ValueError('Less than 5 GiB free.')
            from datetime import datetime
            self.folder=folder/datetime.now().strftime('%Y%m%d_%H%M%S_%f');self.folder.mkdir()
            self.gate.clear();self.armed=set();self.done=set();self.running=True;self.stopping=False;self.preparing=time.perf_counter();self.locked(True)
            jobs=[]
            for i in sorted(self.active):
                s=self.slots[i]
                job=dict(folder=str(self.folder),camera=self.camera_vars[i].get(),animal=self.id_vars[i].get(),stem=file_stem(i,self.camera_vars[i].get(),self.id_vars[i].get()),minutes=minutes,segment=segment,format=self.format.get())
                jobs.append(dict(job=job,source=s['source'],capture=s['capture']))
                s['cmd'].put(dict(action='prepare',job=job));self.update_name(i)
            (self.folder/'session.json').write_text(json.dumps(jobs,indent=2),encoding='utf-8');self.note('Preparing encoders. Output: '+str(self.folder))
        except Exception as exc:
            if self.running:self.stop()
            messagebox.showerror('Cannot record',str(exc))
    def stop(self):
        if self.running and not self.stopping:
            self.stopping=True
            for s in self.slots:
                if s and s['process'].is_alive():s['cmd'].put(dict(action='stop'))
            self.note('Closing recordings; live previews will continue.')
    def close(self):
        self.closing=True
        if self.running:self.stop()
        else:self.disconnect()
    def poll(self):
        now=time.perf_counter()
        if self.scan_process:
            result=None
            try:result=self.scan_q.get_nowait()
            except queue.Empty:pass
            exited=not self.scan_process.is_alive() and now-self.scan_time>2
            limit=5 if self.scan_stage=='probe' else 20
            if result or now-self.scan_time>limit or exited:
                if self.scan_stage=='names':
                    if result and result[0]=='devices' and result[1]:
                        self.checked_devices=result[1];self.check_index=0
                        self.cancel_scan()
                        self.install_sources(self.checked_devices)
                        self.next_probe()
                    else:
                        reason=str(result[1]) if result and result[0]=='error' else ('zero named devices' if result else 'scan timeout / scanner exit')
                        self.cancel_scan()
                        self.install_sources(index_sources(self.scan_backend))
                        self.scan_status.set('Name scan failed: '+reason+' | Index list is available. Verify sources using preview.')
                        self.note('Source enumeration failed: '+reason)
                else:
                    device=self.checked_devices[self.check_index]
                    device['availability']=result[1] if result and result[0]=='probe' else 'TIMEOUT'
                    self.cancel_scan()
                    self.check_index+=1
                    self.install_sources(self.checked_devices)
                    self.next_probe()
        while True:
            try:e=self.events.get_nowait()
            except queue.Empty:break
            i=e['slot'];kind=e['kind'];s=self.slots[i]
            if not s or e.get('connection')!=s['source'].get('connection'):continue
            if kind=='connected':
                s['actual']=e['actual'];self.note(f'Slot {i+1} actual capture: {e["actual"]}')
            elif kind=='warning':self.note(f'Channel {i+1} WARNING: '+e['message'])
            elif kind=='armed':self.armed.add(i)
            elif kind=='status':
                s['healthy']=True
                mode='RECORDING' if e['recording'] else 'LIVE PREVIEW - NOT RECORDING'
                a=e['actual'];self.status[i].configure(text=f'{mode}\nActual {a["width"]}x{a["height"]} / {a["input_fourcc"]} / driver {a["reported_fps"]:.1f} fps\nMeasured {e["live_fps"]} fps | saved {e["frames"]} frames | {e["elapsed"]} s')
            elif kind=='signal_lost':
                s['healthy']=False;self.no_signal(i,'Camera read failed.')
            elif kind=='signal_restored':s['healthy']=True
            elif kind=='error':
                s['healthy']=False;self.no_signal(i,e['message']);self.note(f'Slot {i+1} ERROR: '+e['message'])
                if self.running:self.stop()
            elif kind=='record_done':
                self.done.add(i);self.note(f'Slot {i+1}: saved {e["frames"]} frames ({e["reason"]})')
        if self.running and not self.stopping and self.active.issubset(self.armed) and not self.gate.is_set():
            self.epoch.value=time.perf_counter();self.gate.set()
            (self.folder/'start_timing.json').write_text(json.dumps(dict(host_monotonic_epoch=self.epoch.value,host_unix_ns=time.time_ns()),indent=2))
            self.note('RECORDING started. Shared software start signal released.')
        if self.running and not self.gate.is_set() and now-self.preparing>15 and not self.stopping:
            self.note('Encoder preparation timeout.');self.stop()
        for i,s in enumerate(self.slots):
            if not s:continue
            try:
                stamp,data=s['images'].get_nowait()
                if now-stamp<2 and 'disconnect_time' not in s:
                    from PIL import Image,ImageTk
                    self.badges[i].configure(text='CONNECTED',foreground='#157b2d')
                    self.photos[i]=ImageTk.PhotoImage(Image.open(io.BytesIO(data)));self.labels[i].configure(image=self.photos[i],text='');self.live[i]=stamp;s['last_frame']=stamp;s['healthy']=True
            except queue.Empty:pass
            age=now-s.get('last_frame',s['opened'])
            if age>3:self.no_signal(i,'No fresh video frames. Check source / USB connection.')
            if age>15 and self.running and not self.stopping:self.note(f'Slot {i+1} unresponsive.');self.stop()
            if 'disconnect_time' in s and now-s['disconnect_time']>5 and not self.running and s['process'].is_alive():s['process'].terminate()
            if not s['process'].is_alive():
                s['process'].join(.1)
                if self.running and i in self.active and i not in self.done:self.done.add(i);self.note(f'Slot {i+1} source closed during session.');self.stop()
                s['cmd'].close();s['images'].close();self.slots[i]=None;self.no_signal(i,'Source disconnected. Reselect to reconnect.')
                if i in self.pending:self.open_pending(i)
        if self.running:
            try:
                free=shutil.disk_usage(self.folder).free/1024**3
                self.info.configure(text=f'Free disk {free:.1f} GiB | Output: {self.folder}')
                if free<2:self.stop()
            except OSError:self.stop()
            if self.active.issubset(self.done):
                self.running=False;self.gate.clear();self.locked(False);self.note('Recording finished. Live previews remain active.')
                try:(self.folder/'gui_log.txt').write_text(self.log.get('1.0','end'),encoding='utf-8')
                except OSError as exc:self.note(str(exc))
                if self.closing:self.disconnect()
        if self.closing and not self.running:
            if any(s and not s['quit'].is_set() for s in self.slots):self.disconnect()
            if not any(self.slots):
                if self.scan_process and self.scan_process.is_alive():self.scan_process.terminate()
                self.root.destroy();return
        self.root.after(100,self.poll)


if __name__=='__main__':
    mp.freeze_support()
    root=tk.Tk();App(root);root.mainloop()
