"""Validate JSON and change only whitespace between lexical tokens."""
import argparse
import json
import os
from pathlib import Path
import queue
import re
import stat
import sys
import tempfile
import threading

MAX_INPUT = 10 * 1024 * 1024
MAX_OUTPUT = 50 * 1024 * 1024
MAX_DEPTH = 64
TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null|[{}\[\],:]')

def cancel(event):
    if event is not None and event.is_set():
        raise InterruptedError('已取消，未发布输出文件。')

def linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)

def identity(info):
    value = info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
    return value if os.name == 'nt' else value + (info.st_ctime_ns,)

def ordinary_directory(path):
    for parent in (path, *path.parents):
        info = parent.lstat()
        if linked(info) or not stat.S_ISDIR(info.st_mode):
            raise ValueError('路径包含链接或非文件夹。')

def pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError(f'对象含重复键：{key!r}')
        value[key] = item
    return value

def constant(value):
    raise ValueError(f'非标准 JSON 数字：{value}')

def format_text(text, *, compact=False, indent=2, event=None):
    if indent not in {2, 4}:
        raise ValueError('缩进仅支持 2 或 4 个空格。')
    cancel(event)
    # Preflight nesting before decoding, so deep input never reaches recursion.
    depth = 0
    for match in TOKEN.finditer(text):
        cancel(event)
        token = match.group()
        if token in ('{', '['):
            depth += 1
            if depth > MAX_DEPTH:
                raise ValueError('JSON 嵌套上限 64 层。')
        elif token in ('}', ']'):
            depth -= 1
    value = json.loads(text, parse_int=str, parse_float=str, parse_constant=constant, object_pairs_hook=pairs)
    cancel(event)
    tokens = [match.group() for match in TOKEN.finditer(text)]
    pieces, depth, size = [], 0, 0
    def append(piece):
        nonlocal size
        size += len(piece.encode('utf-8'))
        if size > MAX_OUTPUT:
            raise ValueError('格式化输出超过 50 MiB。')
        pieces.append(piece)
    for index, token in enumerate(tokens):
        cancel(event)
        previous = tokens[index - 1] if index else ''
        following = tokens[index + 1] if index + 1 < len(tokens) else ''
        if token in ('{', '['):
            append(token)
            depth += 1
            if not compact and following != ('}' if token == '{' else ']'):
                append('\n' + ' ' * (depth * indent))
        elif token in ('}', ']'):
            depth -= 1
            if not compact and previous != ('{' if token == '}' else '['):
                append('\n' + ' ' * (depth * indent))
            append(token)
        elif token == ',':
            append(',' if compact else ',\n' + ' ' * (depth * indent))
        elif token == ':':
            append(':' if compact else ': ')
        else:
            append(token)
    if not compact:
        append('\n')
    return ''.join(pieces), 'object' if isinstance(value, dict) else 'array' if isinstance(value, list) else 'scalar'

def process(source, output=None, *, compact=False, indent=2, event=None):
    path = Path(source).absolute()
    ordinary_directory(path.parent)
    before = path.lstat()
    if linked(before) or not stat.S_ISREG(before.st_mode):
        raise ValueError('输入必须是普通文件，不能是链接。')
    if before.st_size > MAX_INPUT:
        raise ValueError('输入 JSON 上限 10 MiB。')
    target = Path(output).absolute() if output is not None else None
    if target is not None:
        ordinary_directory(target.parent)
        if os.path.lexists(target) or target.resolve() == path.resolve():
            raise FileExistsError('输出必须是新文件，不能覆盖已有文件或输入。')
    cancel(event)
    with path.open('rb') as stream:
        if identity(os.fstat(stream.fileno())) != identity(before):
            raise OSError('输入在打开时发生变化。')
        data = stream.read(MAX_INPUT + 1)
        if len(data) > MAX_INPUT or identity(os.fstat(stream.fileno())) != identity(before):
            raise OSError('输入在读取时变化或超过大小限制。')
    if identity(path.lstat()) != identity(before):
        raise OSError('输入在读取后发生变化。')
    formatted, kind = format_text(data.decode('utf-8-sig', errors='strict'), compact=compact, indent=indent, event=event)
    payload = formatted.encode('utf-8')
    result = {'valid': True, 'top_level': kind, 'input_bytes': len(data), 'output_bytes': len(payload),
        'mode': 'compact' if compact else f'indent-{indent}', 'preview': formatted[:50000]}
    if target is not None:
        cancel(event)
        fd, name = tempfile.mkstemp(prefix='.json-format-', suffix='.tmp', dir=target.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, 'wb') as destination:
                for start in range(0, len(payload), 1024 * 1024):
                    cancel(event)
                    destination.write(payload[start:start + 1024 * 1024])
                destination.flush()
                os.fsync(destination.fileno())
            cancel(event)
            if os.name == 'nt':
                os.rename(temporary, target)
            else:
                os.link(temporary, target)
                temporary.unlink()
            result['output'] = str(target)
        finally:
            if temporary.exists():
                temporary.unlink()
    else:
        cancel(event)
    return result

def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    root = tk.Tk()
    root.title('JSON 格式化与检查器')
    root.geometry('880x630')
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='检查标准 JSON；格式化或压缩结构空白，保留键顺序、数字及字符串原写法。').pack(anchor='w')
    source, output = tk.StringVar(), tk.StringVar()
    controls = []
    def row(label, variable, browse):
        bar = ttk.Frame(frame)
        bar.pack(fill='x', pady=8)
        ttk.Label(bar, text=label, width=10).pack(side='left')
        entry = ttk.Entry(bar, textvariable=variable)
        entry.pack(side='left', fill='x', expand=True)
        button = ttk.Button(bar, text='选择', command=browse)
        button.pack(side='left', padx=8)
        controls.extend([entry, button])
    def choose_source():
        value = filedialog.askopenfilename(filetypes=[('JSON 文件', '*.json'), ('所有文件', '*.*')])
        if value:
            source.set(value)
            path = Path(value)
            output.set(str(path.with_name(path.stem + '-格式化.json')))
    def choose_output():
        value = filedialog.asksaveasfilename(title='选择尚不存在的新文件', defaultextension='.json')
        if value:
            output.set(value)
    row('输入 JSON', source, choose_source)
    row('新输出文件', output, choose_output)
    bar = ttk.Frame(frame)
    bar.pack(fill='x', pady=8)
    compact = tk.BooleanVar(value=False)
    check = ttk.Checkbutton(bar, text='压缩（移除结构空白）', variable=compact)
    check.pack(side='left')
    controls.append(check)
    ttk.Label(bar, text='缩进').pack(side='left', padx=12)
    indent = tk.StringVar(value='2')
    box = ttk.Combobox(bar, textvariable=indent, values=['2', '4'], state='readonly', width=5)
    box.pack(side='left')
    controls.append(box)
    preview = tk.Text(frame, height=17, wrap='none', state='disabled')
    preview.pack(fill='both', expand=True, pady=8)
    status = tk.StringVar(value='输入 UTF-8/BOM，最多 10 MiB、64 层。预览最多 50000 字符。保存时重新读取。')
    ttk.Label(frame, textvariable=status, wraplength=830).pack(anchor='w', pady=8)
    messages, event = queue.Queue(), threading.Event()
    state = {'busy': False, 'closing': False}
    def start(save):
        if not source.get().strip() or save and not output.get().strip():
            messagebox.showerror('缺少路径', '请选择输入和新输出文件。')
            return
        args = source.get(), output.get() if save else None
        kwargs = dict(compact=compact.get(), indent=int(indent.get()), event=event)
        event.clear()
        state['busy'] = True
        for control in controls:
            control.configure(state='disabled')
        stop.configure(state='normal')
        status.set('正在检查并格式化…')
        def worker():
            try:
                messages.put(('ok', process(*args, **kwargs)))
            except Exception as error:
                messages.put(('error', str(error)))
        threading.Thread(target=worker, daemon=True).start()
    bar = ttk.Frame(frame)
    bar.pack(fill='x')
    for label, save in [('检查 / 预览', False), ('保存新文件', True)]:
        button = ttk.Button(bar, text=label, command=lambda s=save: start(s))
        button.pack(side='left', padx=4)
        controls.append(button)
    stop = ttk.Button(bar, text='取消', state='disabled', command=event.set)
    stop.pack(side='left', padx=8)
    def close():
        if state['busy']:
            state['closing'] = True
            event.set()
            status.set('正在取消，等待临时文件清理…')
        else:
            root.destroy()
    def poll():
        try:
            kind, data = messages.get_nowait()
        except queue.Empty:
            root.after(100, poll)
            return
        state['busy'] = False
        if state['closing']:
            root.destroy()
            return
        for control in controls:
            control.configure(state='readonly' if control is box else 'normal')
        stop.configure(state='disabled')
        preview.configure(state='normal')
        preview.delete('1.0', 'end')
        if kind == 'error':
            status.set(data)
        else:
            preview.insert('1.0', data['preview'])
            status.set(f"JSON 有效；{data['input_bytes']} → {data['output_bytes']} 字节。" + ('已保存：' + data['output'] if 'output' in data else '预览完成。'))
        preview.configure(state='disabled')
        root.after(100, poll)
    root.protocol('WM_DELETE_WINDOW', close)
    root.after(100, poll)
    root.mainloop()

def main():
    parser = argparse.ArgumentParser(description='JSON 检查、格式化或压缩；仅修改结构空白，不覆盖源文件。')
    parser.add_argument('input')
    parser.add_argument('--output', help='不指定时只检查/预览')
    parser.add_argument('--compact', action='store_true')
    parser.add_argument('--indent', type=int, choices=[2, 4], default=2)
    args = parser.parse_args()
    try:
        print(json.dumps(process(args.input, args.output, compact=args.compact, indent=args.indent), ensure_ascii=True))
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=True), file=sys.stderr)
        return 2

if __name__ == '__main__':
    if len(sys.argv) == 1:
        gui()
    else:
        raise SystemExit(main())
