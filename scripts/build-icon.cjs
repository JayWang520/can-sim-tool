// Rebuild the Windows multi-resolution icon from the canonical SVG.
// npm install --prefix build/icon-tools --no-save --package-lock=false @resvg/resvg-js
const fs = require('node:fs');
const path = require('node:path');
const {Resvg} = require('../build/icon-tools/node_modules/@resvg/resvg-js');
const root = path.resolve(__dirname, '..');
const svg = fs.readFileSync(path.join(root, 'web/icon.svg'), 'utf8');
const sizes = [16, 20, 24, 32, 48, 64, 128, 256];
const images = sizes.map(size => new Resvg(svg, {fitTo: {mode:'width', value:size}}).render().asPng());
const header = Buffer.alloc(6 + 16 * sizes.length);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(sizes.length, 4);
let offset = header.length;
sizes.forEach((size, i) => {
  const entry = 6 + i * 16;
  header[entry] = size === 256 ? 0 : size;
  header[entry + 1] = header[entry];
  header.writeUInt16LE(1, entry + 4);
  header.writeUInt16LE(32, entry + 6);
  header.writeUInt32LE(images[i].length, entry + 8);
  header.writeUInt32LE(offset, entry + 12);
  offset += images[i].length;
});
fs.writeFileSync(path.join(root, 'web/icon.ico'), Buffer.concat([header, ...images]));
fs.writeFileSync(path.join(root, 'build/icon-preview.png'), images.at(-1));
console.log(`Built icon.ico: ${sizes.join(', ')} px`);
