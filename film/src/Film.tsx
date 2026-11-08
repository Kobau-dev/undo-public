// Sober cut: the pages and the subtitles, nothing around them. How the takes were made is on the end card.
// The pointers are in the recordings: the real one, and Undo's own cursor when it acts. Nothing is drawn over them.
import React from 'react';
import {
  AbsoluteFill, Audio, Easing, OffthreadVideo, Sequence, interpolate, staticFile, useCurrentFrame,
} from 'remotion';
import {
  Clip, FPS, FRAME, Focus, SCREEN, TOP, TOTAL_FRAMES, Video, disclosure, itemFrames, items, srcRangeToFrames, srcToFrame,
  starts, takes, voCues, voDur, voText,
} from './timeline';

// ---- layout ---------------------------------------------------------------------------------------------------
const {w: W, h: H} = FRAME;
const SW = W;
const SH = Math.round((SW * SCREEN.h) / SCREEN.w); // 1206: the page, edge to edge
const K = SW / SCREEN.w; // px per screen point

const FONT = '-apple-system, "SF Pro Display", "SF Pro Text", "Helvetica Neue", Inter, Arial, sans-serif';
const C = {bg: '#000', text: '#eceef3', muted: '#8a92a6', accent: '#4c8dff', user: '#d7dbe4'};

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
const smooth = Easing.bezier(0.45, 0, 0.2, 1);
const hold = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

// ---- camera -----------------------------------------------------------------------------------------------------
type Rect = {left: number; top: number; s: number};
const rectOf = (f: Focus): Rect => {
  const vw = SCREEN.w / f.s;
  const vh = SCREEN.h / f.s;
  return {left: clamp(f.x - vw / 2, 0, SCREEN.w - vw), top: clamp(f.y - TOP - vh / 2, 0, SCREEN.h - vh), s: f.s};
};
const lerpRect = (a: Rect, b: Rect, u: number): Rect => ({
  left: a.left + (b.left - a.left) * u, top: a.top + (b.top - a.top) * u, s: a.s + (b.s - a.s) * u,
});

// ---- the take ---------------------------------------------------------------------------------------------------
const ClipView: React.FC<{clip: Clip}> = ({clip}) => {
  const f = useCurrentFrame();
  const total = itemFrames(clip);
  const zoomFrames = clip.zoomSec ? clip.zoomSec * FPS : total - 1;
  const u = smooth(clamp(f / Math.max(1, zoomFrames), 0, 1));
  const cam = lerpRect(rectOf(clip.zoomFrom), rectOf(clip.zoomTo ?? clip.zoomFrom), u);
  const take = takes[clip.video];

  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      <div style={{
        position: 'absolute', left: 0, top: 0, width: SW, height: SH, transformOrigin: '0 0',
        transform: `translate(${-cam.left * K * cam.s}px, ${-cam.top * K * cam.s}px) scale(${cam.s})`,
      }}>
        <OffthreadVideo src={staticFile(`takes/${clip.video}.mp4`)} muted
          startFrom={Math.round(clip.from * FPS)} endAt={Math.round(clip.to * FPS) + 1} playbackRate={clip.rate}
          style={{width: SW, height: SH}} />
        {(take.masks ?? []).map((m) => (
          <div key={`${m.x}-${m.y}`} style={{
            position: 'absolute', left: m.x * K, top: (m.y - TOP) * K, width: m.w * K, height: m.h * K, background: m.color,
          }} />
        ))}
      </div>
    </AbsoluteFill>
  );
};

/** Current clip and its opacity: a short fade only where the take changes. */
const currentClip = (frame: number) => {
  const idx = items.findIndex((i) => frame >= starts[i.id] && frame < starts[i.id] + itemFrames(i));
  const it = items[idx];
  if (!it || it.kind !== 'clip') return null;
  const video = (o: (typeof items)[number] | undefined) => (o?.kind === 'clip' ? o.video : null);
  const local = frame - starts[it.id];
  const n = itemFrames(it);
  const fin = video(items[idx - 1]) === it.video ? 1 : interpolate(local, [0, 7], [0, 1], hold);
  const fout = video(items[idx + 1]) === it.video ? 1 : interpolate(local, [n - 7, n - 1], [1, 0], hold);
  return {clip: it, opacity: Math.min(fin, fout)};
};

const ClipStage: React.FC<{clip: Clip}> = ({clip}) => {
  const f = useCurrentFrame();
  const opacity = currentClip(starts[clip.id] + f)?.opacity ?? 1;
  return (
    <div style={{position: 'absolute', left: 0, top: 0, width: SW, height: SH, opacity, overflow: 'hidden', background: '#000'}}>
      <ClipView clip={clip} />
    </div>
  );
};

/** The cut between two recordings: says how much real time separates them. */
const GapCard: React.FC<{text: string; note: string; frames: number}> = ({text, note, frames}) => {
  const f = useCurrentFrame();
  const a = interpolate(f, [0, 6, frames - 6, frames], [0, 1, 1, 0], hold);
  return (
    <AbsoluteFill style={{background: C.bg, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14}}>
      <div style={{opacity: a, font: `600 68px ${FONT}`, color: C.text}}>{text}</div>
      <div style={{opacity: a, font: `500 30px ${FONT}`, color: C.muted}}>{note}</div>
    </AbsoluteFill>
  );
};

// ---- subtitles --------------------------------------------------------------------------------------------------
const cueFrame = (c: (typeof voCues)[number]) => starts[c.clip] + Math.round(c.at * FPS);

const Captions: React.FC = () => {
  const frame = useCurrentFrame();
  const cue = voCues.find((c) => frame >= cueFrame(c) && frame < cueFrame(c) + Math.round(voDur[c.id] * FPS) + 8);
  if (!cue) return null;
  const st = cueFrame(cue);
  const en = st + Math.round(voDur[cue.id] * FPS) + 8;
  const a = interpolate(frame, [st, st + 5, en - 5, en], [0, 1, 1, 0], hold);
  return (
    <div style={{
      position: 'absolute', left: 60, width: W - 120, top: SH, height: H - SH, display: 'flex', alignItems: 'center', justifyContent: 'center',
      textAlign: 'center', opacity: a, font: `${cue.user ? 'italic 500' : '500'} 34px/1.28 ${FONT}`, color: cue.user ? C.user : C.text,
    }}>
      <div>{cue.user ? (<><span style={{color: C.accent, fontStyle: 'normal', marginRight: 12}}>●</span>“{voText[cue.id]}”</>) : voText[cue.id]}</div>
    </div>
  );
};

// ---- end ---------------------------------------------------------------------------------------------------------
const End: React.FC = () => {
  const f = useCurrentFrame();
  const a = interpolate(f, [0, 10], [0, 1], hold);
  return (
    <AbsoluteFill style={{background: C.bg, opacity: a}}>
      <div style={{
        position: 'absolute', left: 0, top: 0, width: W, height: SH, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 22,
      }}>
        <div style={{font: `700 124px ${FONT}`, color: C.text, letterSpacing: -1}}>Undo</div>
        <div style={{font: `500 42px ${FONT}`, color: C.text}}>github.com/Kobau-dev/undo-public</div>
        <div style={{font: `500 28px ${FONT}`, color: C.muted, marginTop: 8}}>Holo · H Company — Gladia — Apple Vision</div>
      </div>
      <div style={{position: 'absolute', left: 60, width: W - 120, top: SH - 110, textAlign: 'center', font: `500 23px/1.45 ${FONT}`, color: C.muted}}>
        {disclosure.map((line) => <div key={line}>{line}</div>)}
      </div>
    </AbsoluteFill>
  );
};

// ---- audio: the voices, discreet clicks and keys, a very low bed ------------------------------------------------------
const sfx = (name: string) => staticFile(`sfx/${name}.wav`);

const voRanges = voCues.map((c) => [cueFrame(c), cueFrame(c) + Math.round(voDur[c.id] * FPS)] as const);
const musicVolume = (f: number) => {
  const inVo = voRanges.some(([a, b]) => f >= a - 6 && f <= b + 10);
  const base = inVo ? 0.05 : 0.1;
  const fadeIn = interpolate(f, [0, 20], [0, 1], hold);
  const fadeOut = interpolate(f, [TOTAL_FRAMES - 60, TOTAL_FRAMES], [1, 0], hold);
  return base * fadeIn * fadeOut;
};

const Sfx: React.FC<{at: number | null; name: string; volume?: number; frames?: number}> = ({at, name, volume = 1, frames = 45}) =>
  at === null || at < 0 ? null : (
    <Sequence from={at} durationInFrames={frames} layout="none">
      <Audio src={sfx(name)} volume={volume} />
    </Sequence>
  );

const SoundTrack: React.FC = () => {
  const nodes: React.ReactNode[] = [];
  voCues.forEach((c) => nodes.push(
    <Sequence key={`vo-${c.id}`} from={cueFrame(c)} durationInFrames={Math.round(voDur[c.id] * FPS) + 6} layout="none">
      <Audio src={staticFile(`vo/${c.id}.mp3`)} volume={1} />
    </Sequence>,
  ));
  (Object.keys(takes) as Video[]).forEach((v) => {
    const t = takes[v];
    t.clicks.forEach((c, i) => {
      const seg = srcRangeToFrames(v, c, c + 0.01)[0];
      if (seg && seg.rate <= 8) nodes.push(<Sfx key={`cl-${v}-${i}`} at={seg.start} name="click" volume={0.5} frames={10} />);
    });
    t.agentClicks.forEach((c, i) => nodes.push(<Sfx key={`ac-${v}-${i}`} at={srcToFrame(v, c)} name="click" volume={0.5} frames={10} />));
    t.keys.forEach((k, i) => {
      for (let j = 0; j < (k.repeat ?? 1); j++) {
        const name = k.label === '⇧ ⇧' ? 'double_shift' : 'shortcut';
        nodes.push(<Sfx key={`k-${v}-${i}-${j}`} at={srcToFrame(v, k.t + j * (k.every ?? 0))} name={name} volume={0.45} frames={20} />);
      }
    });
    t.typing.forEach((r, i) => srcRangeToFrames(v, r.from, r.to).forEach((seg, j) => {
      if (seg.rate > 3) return;
      nodes.push(
        <Sequence key={`ty-${v}-${i}-${j}`} from={seg.start} durationInFrames={seg.frames} layout="none">
          <Audio src={sfx(r.who === 'user' ? 'typing_user' : 'typing_agent')} volume={0.12} />
        </Sequence>,
      );
    }));
  });
  return (
    <>
      <Audio src={sfx('music')} volume={musicVolume} />
      {nodes}
    </>
  );
};

// ---- film -------------------------------------------------------------------------------------------------------
export const Film: React.FC = () => (
  <AbsoluteFill style={{background: C.bg, fontFamily: FONT}}>
    {items.map((it) => (
      <Sequence key={it.id} from={starts[it.id]} durationInFrames={itemFrames(it)} layout="none">
        {it.kind === 'end' ? <End /> : it.kind === 'gap' ? <GapCard text={it.text} note={it.note} frames={itemFrames(it)} /> : <ClipStage clip={it} />}
      </Sequence>
    ))}
    <Captions />
    <SoundTrack />
  </AbsoluteFill>
);
