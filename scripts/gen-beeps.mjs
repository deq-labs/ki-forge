// Writes the timer beeps (apps/mobile/assets/sounds/*.wav): `node scripts/gen-beeps.mjs apps/mobile/assets/sounds`.
import { writeFileSync } from 'node:fs';
// 16-bit mono PCM WAV, sine with a short attack/release so it doesn't click.
function wav(path, tones, rate = 44100) {
  const samples = [];
  for (const { hz, ms, gap = 0 } of tones) {
    const n = Math.round((rate * ms) / 1000);
    const edge = Math.round(rate * 0.006);
    for (let i = 0; i < n; i++) {
      const env = Math.min(1, i / edge, (n - i) / edge);
      // A little second harmonic so it cuts through gym noise.
      const s = Math.sin((2 * Math.PI * hz * i) / rate) * 0.8 + Math.sin((4 * Math.PI * hz * i) / rate) * 0.2;
      samples.push(Math.round(s * env * 0.9 * 32767));
    }
    for (let i = 0; i < Math.round((rate * gap) / 1000); i++) samples.push(0);
  }
  const data = Buffer.alloc(samples.length * 2);
  samples.forEach((v, i) => data.writeInt16LE(v, i * 2));
  const h = Buffer.alloc(44);
  h.write('RIFF', 0); h.writeUInt32LE(36 + data.length, 4); h.write('WAVE', 8);
  h.write('fmt ', 12); h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22);
  h.writeUInt32LE(rate, 24); h.writeUInt32LE(rate * 2, 28); h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34);
  h.write('data', 36); h.writeUInt32LE(data.length, 40);
  writeFileSync(path, Buffer.concat([h, data]));
}
const dir = process.argv[2];
wav(`${dir}/tick.wav`, [{ hz: 880, ms: 140 }]);
wav(`${dir}/go.wav`, [{ hz: 1320, ms: 420 }]);
wav(`${dir}/done.wav`, [{ hz: 1320, ms: 160, gap: 70 }, { hz: 1320, ms: 160, gap: 70 }, { hz: 1760, ms: 420 }]);
