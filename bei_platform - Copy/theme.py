"""Shared light/dark palette for Tk/ttk and analytic canvases."""
import tkinter as tk
from tkinter import ttk
import json
from pathlib import Path

P = {
 'light': {'bg':'#FFFFFF','panel':'#FFFFFF','input':'#F5F8FD','text':'#0D2247','muted':'#526679','border':'#DCE5F0','selected':'#DCEBFF','accent':'#1E73D8','grid':'#E8EDF3'},
 'dark': {'bg':'#0B1220','panel':'#152238','input':'#1E304A','text':'#EDF4FF','muted':'#ACBDD7','border':'#344761','selected':'#28466B','accent':'#54A9FF','grid':'#344761'},
}

# Named RGB literals already embedded in the legacy charts. Theme only neutral
# surfaces/labels, keeping green/red direction signals unchanged.
NEUTRAL = {
 '#ffffff':'panel','#fff':'panel','#f5f8fd':'input','#f3f7fc':'input',
 '#eef3fa':'input','#f6f9fd':'input','#f8fafc':'input',
 '#dce3ec':'border','#dce5f0':'border','#d1dae6':'border','#e8edf3':'grid',
 '#e9eff5':'grid','#9aa8b7':'muted','#a1adbb':'muted','#9eacbc':'muted',
 '#425a72':'muted','#526679':'muted','#48576b':'muted','#586778':'muted',
 '#59697a':'muted','#66788b':'muted','#66798c':'muted','#6b7280':'muted',
 '#18324b':'text','#0d2247':'text','#325574':'text','#273b5a':'text',
}

def _theme_of(widget):
 try:return widget.winfo_toplevel().theme_mode.get()
 except Exception:return 'light'

def _color(widget, val):
 if not isinstance(val,str):return val
 key=NEUTRAL.get(val.lower())
 if key:return P[_theme_of(widget)][key]
 if _theme_of(widget)=='dark':
  if val.lower() in ('black','#000000'):return P['dark']['text']
  if val.lower()=='white':return P['dark']['panel']
 return val

class ThemeCanvas(tk.Canvas):
 def __init__(self,master=None,**kwargs):
  kwargs['bg']=P[_theme_of(master)]['panel']
  kwargs['highlightbackground']=P[_theme_of(master)]['border']
  super().__init__(master,**kwargs)
  self._source_styles={}
 def _make(self,method,args,kwargs):
  source={k:v for k,v in kwargs.items() if k in ('fill','outline')}
  transformed={k:(_color(self,v) if k in source else v) for k,v in kwargs.items()}
  iid=getattr(super(),method)(*args,**transformed)
  if source:self._source_styles[iid]=source
  return iid
 def create_line(self,*args,**kwargs):return self._make('create_line',args,kwargs)
 def create_rectangle(self,*args,**kwargs):return self._make('create_rectangle',args,kwargs)
 def create_text(self,*args,**kwargs):return self._make('create_text',args,kwargs)
 def create_oval(self,*args,**kwargs):return self._make('create_oval',args,kwargs)
 def create_polygon(self,*args,**kwargs):return self._make('create_polygon',args,kwargs)
 def create_arc(self,*args,**kwargs):return self._make('create_arc',args,kwargs)
 def delete(self,*args):
  super().delete(*args)
  alive=set(self.find_all())
  self._source_styles={k:v for k,v in self._source_styles.items() if k in alive}
 def apply_theme(self):
  pal=P[_theme_of(self)]
  self.configure(bg=pal['panel'],highlightbackground=pal['border'])
  for iid,source in list(self._source_styles.items()):
   try:self.itemconfigure(iid,**{k:_color(self,v) for k,v in source.items()})
   except tk.TclError:pass

def config_path(root):return Path(__file__).resolve().parent.parent/'ui_preferences.json'
def load_mode(root):
 try:
  mode=json.loads(config_path(root).read_text(encoding='utf-8')).get('theme','light')
  return mode if mode in P else 'light'
 except (OSError,ValueError,TypeError):return 'light'
def save_mode(root,mode):
 try:config_path(root).write_text(json.dumps({'theme':mode},indent=2),encoding='utf-8')
 except OSError:pass

def apply_theme(root,mode):
 pal=P[mode];root.configure(bg=pal['bg'])
 style=ttk.Style(root)
 try:style.theme_use('clam')
 except tk.TclError:pass
 style.configure('.',background=pal['bg'],foreground=pal['text'],font=('Segoe UI',9))
 style.configure('TFrame',background=pal['bg'])
 style.configure('TLabelframe',background=pal['bg'],bordercolor=pal['border'])
 style.configure('TLabelframe.Label',background=pal['bg'],foreground=pal['text'])
 style.configure('TLabel',background=pal['bg'],foreground=pal['text'])
 style.configure('Title.TLabel',background=pal['bg'],foreground=pal['text'],font=('Segoe UI',18,'bold'))
 style.configure('TButton',background=pal['input'],foreground=pal['text'],padding=(8,5),bordercolor=pal['border'])
 style.map('TButton',background=[('active',pal['selected'])],foreground=[('disabled',pal['muted'])])
 style.configure('TNotebook',background=pal['bg'],bordercolor=pal['border'])
 style.configure('TNotebook.Tab',background=pal['input'],foreground=pal['text'],padding=(11,7))
 style.map('TNotebook.Tab',background=[('selected',pal['panel']),('active',pal['selected'])],foreground=[('selected',pal['accent'])])
 style.configure('TEntry',fieldbackground=pal['input'],foreground=pal['text'],insertcolor=pal['text'],bordercolor=pal['border'])
 style.configure('TCombobox',fieldbackground=pal['input'],background=pal['input'],foreground=pal['text'],arrowcolor=pal['text'])
 style.map('TCombobox',fieldbackground=[('readonly',pal['input'])],foreground=[('readonly',pal['text'])])
 style.configure('Treeview',background=pal['panel'],fieldbackground=pal['panel'],foreground=pal['text'],rowheight=25,bordercolor=pal['border'])
 style.map('Treeview',background=[('selected',pal['selected'])],foreground=[('selected',pal['text'])])
 style.configure('Treeview.Heading',background=pal['input'],foreground=pal['text'])
 style.configure('TScrollbar',background=pal['input'],troughcolor=pal['bg'],arrowcolor=pal['text'])
 style.configure('TPanedwindow',background=pal['border'])
 style.configure('TSeparator',background=pal['border'])
 try:root.option_add('*TCombobox*Listbox.background',pal['input']);root.option_add('*TCombobox*Listbox.foreground',pal['text'])
 except tk.TclError:pass
 def walk(parent):
  for child in parent.winfo_children():
   if isinstance(child,ThemeCanvas):child.apply_theme()
   elif isinstance(child,tk.Text):
    child.configure(bg=pal['input'],fg=pal['text'],insertbackground=pal['text'],selectbackground=pal['selected'])
   elif isinstance(child,tk.Canvas):
    try:child.configure(bg=pal['panel'],highlightbackground=pal['border'])
    except tk.TclError:pass
   elif isinstance(child,(tk.Frame,tk.Label)):
    try:child.configure(bg=pal['bg'])
    except tk.TclError:pass
   walk(child)
 walk(root)
