"""Actual JSON output/precision/content checks for source and --exe."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

def checks(executable=None):
    command = [str(executable)] if executable else [sys.executable, str(Path(__file__).with_name('json_formatter.py'))]
    def run(*args, code=0):
        result = subprocess.run(command + list(map(str, args)), capture_output=True, timeout=60)
        assert result.returncode == code, (args, result.returncode, result.stdout, result.stderr)
        return json.loads(result.stdout if code == 0 else result.stderr)
    with tempfile.TemporaryDirectory(prefix='JSON-中文-') as folder:
        root = Path(folder)
        source, output = root / '输入.json', root / '格式化.json'
        raw = '{ "数":9007199254740993123456789, "小数":0.123456789012345678901234567890, "负零":-0.00e+10, "文字":"a { \\" q \\\\ [ ] : 中文\\nend", "空":[], "对象":{}, "数组":[1,null,false], "转义":"\\u4e2d" }'
        compact = '{"数":9007199254740993123456789,"小数":0.123456789012345678901234567890,"负零":-0.00e+10,"文字":"a { \\" q \\\\ [ ] : 中文\\nend","空":[],"对象":{},"数组":[1,null,false],"转义":"\\u4e2d"}'
        source.write_bytes(b'\xef\xbb\xbf' + raw.encode('utf-8'))
        original = source.read_bytes()
        preview = run(source)
        assert preview['valid'] and preview['top_level'] == 'object' and not output.exists()
        run(source, '--output', output)
        text = output.read_text(encoding='utf-8')
        assert not output.read_bytes().startswith(b'\xef\xbb\xbf')
        assert text.startswith('{\n  "数": ') and text.endswith('\n')
        assert '\n  "数组": [\n    1,\n    null,\n    false\n  ]' in text
        for token in ['9007199254740993123456789', '0.123456789012345678901234567890', '-0.00e+10', '"\\u4e2d"']:
            assert token in text
        assert json.loads(text, parse_float=Decimal) == json.loads(raw, parse_float=Decimal)
        run(source, '--output', root / '紧凑.json', '--compact')
        assert (root / '紧凑.json').read_text(encoding='utf-8') == compact
        run(source, '--output', root / '四空格.json', '--indent', 4)
        assert (root / '四空格.json').read_text(encoding='utf-8').startswith('{\n    "数": ')
        run(source, '--output', output, code=2)
        run(source, '--output', source, code=2)
        assert source.read_bytes() == original
        for index, scalar in enumerate(['123456789012345678901234567890', '1e999999', 'true', 'null', '"\\ud800"', '[]', '{}']):
            path, target = root / f'scalar-{index}.json', root / f'scalar-{index}-out.json'
            path.write_text(scalar, encoding='utf-8')
            run(path, '--output', target, '--compact')
            assert target.read_text(encoding='utf-8') == scalar
        bad = ['{"a":1,"a":2}', '{"a":1,"\\u0061":2}', '{"x":NaN}', '[Infinity]',
            '[1,]', '{//comment\n"a":1}', '{}{}', '"bad\nstring"', '', '[' * 65 + '0' + ']' * 65]
        for index, text in enumerate(bad):
            path, target = root / f'bad-{index}.json', root / f'bad-{index}-out.json'
            path.write_text(text, encoding='utf-8')
            run(path, '--output', target, code=2)
            assert not target.exists()
        invalid = root / '编码.json'
        invalid.write_bytes(b'\xffbad')
        run(invalid, code=2)
        large = root / '超过大小.json'
        with large.open('wb') as destination:
            destination.truncate(10 * 1024 * 1024 + 1)
        run(large, code=2)
        linked_path = root / '链接.json'
        try:
            linked_path.symlink_to(source)
        except OSError:
            print('SKIP: OS does not permit symlink fixture')
        else:
            run(linked_path, code=2)
        if not executable:
            import json_formatter as tool
            event = threading.Event()
            event.set()
            try:
                tool.process(source, root / 'cancelled.json', event=event)
            except InterruptedError:
                pass
            else:
                raise AssertionError('Cancellation ignored')
            assert not (root / 'cancelled.json').exists()
            event.clear()
            original_fsync = tool.os.fsync
            def cancel_after_flush(descriptor):
                original_fsync(descriptor)
                event.set()
            tool.os.fsync = cancel_after_flush
            try:
                try:
                    tool.process(source, root / 'cancelled-write.json', event=event)
                except InterruptedError:
                    pass
                else:
                    raise AssertionError('Cancellation before publish ignored')
            finally:
                tool.os.fsync = original_fsync
            assert not (root / 'cancelled-write.json').exists()
            old = tool.MAX_OUTPUT
            tool.MAX_OUTPUT = 1
            try:
                try:
                    tool.process(source)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Output limit ignored')
            finally:
                tool.MAX_OUTPUT = old
        assert not list(root.glob('.json-format-*.tmp'))
        print('PASS: actual JSON numeric/string token preservation, BOM/Unicode/format/compact, strict errors/limits/no overwrite/source unchanged', flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path)
    checks(parser.parse_args().exe)
