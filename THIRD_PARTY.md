# Third-party components

## pktctl 0.2.2

The native MCP engine is [pktctl v0.2.2](https://github.com/TantiE100/pktctl/releases/tag/v0.2.2), maintained by Santi E. This repository adds a Python gateway, course-file helpers and scoped Windows controls. pktctl is distributed under the MIT License; installation saves its license as `vendor/LICENSE`.

Pinned Windows x64 archive: `pktctl-0.2.2-x86_64-pc-windows-msvc.zip`.

SHA-256 verified against the published release checksums:

```text
d4914f50e33a0673c78225a591b4ab28884301713a3561abceb126461c0f9cb8
```

```text
MIT License

Copyright (c) 2026 Santi E.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Python dependencies

Direct dependencies are pinned in `requirements.txt`. Installed distributions contain their own license and dependency notices.

| Component | License |
| --- | --- |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | MIT |
| [pypdf](https://github.com/py-pdf/pypdf) | BSD-3-Clause |
| [python-docx](https://github.com/python-openxml/python-docx) | MIT |
| [pywinauto](https://github.com/pywinauto/pywinauto) | BSD-3-Clause |
| [Pillow](https://github.com/python-pillow/Pillow) | MIT-CMU |

## Cisco Packet Tracer

Cisco Packet Tracer is separate software governed by Cisco's terms. The connector uses an existing local installation and does not redistribute Packet Tracer or Cisco's proprietary SDK. This project is not a Cisco product and is not endorsed by Cisco.
