from pathlib import Path
import json
import shutil
import subprocess

import pytest


APP_JS = Path(__file__).parents[1] / "web" / "app.js"


def test_byte_editor_writes_two_digits_before_advancing_to_next_byte():
    source = APP_JS.read_text(encoding="utf-8")

    # Keyboard input is handled once at keydown so duplicate beforeinput
    # events cannot turn one physical key press into two characters.
    assert 'e.target.matches(".byte-editor input")' in source
    assert 'document.addEventListener("keydown"' in source
    assert 'document.addEventListener("beforeinput"' in source
    assert 'e.preventDefault();' in source
    assert 'if (e.repeat) return;' in source
    assert "for (const char of chars) inp = insertByteText(inp, char);" in source
    assert "if (e.target._byteKeyHandled) return;" in source
    assert '.replace(/[^0-9a-fA-F]/g, "").toUpperCase().slice(0, 2)' in source
    assert 'maxlength="2"' in source
    write_current = source.index("inp.value = value;")
    advance_next = source.index("next.focus();")
    assert write_current < advance_next
    assert 'renderByteEditor($("tx-bytes"));' in source
    assert 'renderByteEditor($("tr-send-bytes"));' in source


def test_byte_editor_continuous_input_fills_all_eight_bytes():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the byte-editor JavaScript regression test")

    script = r"""
const fs = require("fs");
const source = fs.readFileSync(process.argv[1], "utf8");
const begin = source.indexOf("function insertByteText");
const end = source.indexOf('document.addEventListener("keydown"', begin);
if (begin < 0 || end < 0) throw new Error("byte editor functions not found");
eval(source.slice(begin, end));

let editor;
const inputs = Array.from({ length: 8 }, (_, i) => ({
  value: "00",
  dataset: { i: String(i) },
  selectionStart: 0,
  selectionEnd: 0,
  closest: () => editor,
  focus() {},
  select() {
    this.selectionStart = 0;
    this.selectionEnd = this.value.length;
  },
  setSelectionRange(start, end) {
    this.selectionStart = start;
    this.selectionEnd = end;
  },
}));
editor = {
  querySelector(selector) {
    const match = selector.match(/data-i="(\d+)"/);
    return match ? inputs[Number(match[1])] || null : null;
  },
};

inputs[0].select();
insertByteSequence(inputs[0], "1");
const single = inputs.map((input) => input.value);

for (const input of inputs) input.value = "00";
inputs[0].select();
insertByteSequence(inputs[0], "1234567890ABCDEF");
const continuous = inputs.map((input) => input.value);
process.stdout.write(JSON.stringify({ single, continuous }));
"""
    result = subprocess.run(
        [node, "-e", script, str(APP_JS)],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(result.stdout)

    assert values["single"] == ["1", "00", "00", "00", "00", "00", "00", "00"]
    assert values["continuous"] == ["12", "34", "56", "78", "90", "AB", "CD", "EF"]
