# Maintainer: Your Name <you@example.com>
pkgname=pulse-monitor
pkgver=1.0.0
pkgrel=2
pkgdesc="PULSE - neon pixel-style system monitor for Arch Linux"
arch=('any')
url="https://github.com/yourusername/pulse-monitor"
license=('MIT')
depends=('python' 'python-pillow')
optdepends=('ttf-press-start-2p: pixel font for the retro look')
source=('pulse.py'
        'pulse.png'
        'pulse.desktop')
sha256sums=('SKIP'
            'SKIP'
            'SKIP')

package() {
  # Executable (force correct shebang)
  install -Dm755 "$srcdir/pulse.py" "$pkgdir/usr/bin/pulse"
  sed -i '1s|.*|#!/usr/bin/env python3|' "$pkgdir/usr/bin/pulse"

  # Icon for menus / window manager
  install -Dm644 "$srcdir/pulse.png" \
    "$pkgdir/usr/share/icons/hicolor/256x256/apps/pulse.png"

  # Desktop entry
  install -Dm644 "$srcdir/pulse.desktop" \
    "$pkgdir/usr/share/applications/pulse.desktop"

  # License
  mkdir -p "$pkgdir/usr/share/licenses/$pkgname"
  cat > "$pkgdir/usr/share/licenses/$pkgname/LICENSE" <<'EOF'
MIT License

Copyright (c) 2026 PULSE Monitor

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
EOF
}