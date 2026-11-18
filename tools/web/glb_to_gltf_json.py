"""Convert .glb files to self-contained glTF JSON (.gltf.json, buffer embedded as base64) so the
claude.ai artifact host (which does not serve .glb) can serve them. three's GLTFLoader reads either.
Usage: python tools/web/glb_to_gltf_json.py web/Dragon.glb web/Rider.glb"""
import base64, json, struct, sys
for path in sys.argv[1:]:
    data = open(path, 'rb').read()
    magic, ver, length = struct.unpack_from('<III', data, 0)
    assert magic == 0x46546C67, path
    off, js, binc = 12, None, b''
    while off < length:
        clen, ctype = struct.unpack_from('<II', data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A: js = json.loads(chunk)
        elif ctype == 0x004E4942: binc = chunk
        off += 8 + clen
    js['buffers'][0]['uri'] = 'data:application/octet-stream;base64,' + base64.b64encode(binc).decode()
    out = path[:-4] + '.gltf.json'
    open(out, 'w').write(json.dumps(js, separators=(',', ':')))
    print(out, round(len(open(out).read()) / 1e6, 2), 'MB')
