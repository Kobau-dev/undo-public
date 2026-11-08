// Edit decision list of the film. All `from`/`to` are seconds in the raw take; `rate` is the speed-up.
// Positions are macOS points of the full screen (1470 x 956); the recordings are cropped below the black notch band.
// The times come from the takes (film/tools/takes.py writes takes.json), so a new take only needs that script run again.
// Story: a tool you don't know well, lost work, then something seen earlier, in that order.
import vo from './vo.json';
import data from './takes.json';

export const FPS = 30;
export const TOP = 33;
export const SCREEN = {w: 1470, h: 956 - TOP};
export const FRAME = {w: 1920, h: 1340}; // the page edge to edge, the subtitles under it

export type Video = 'blender' | 'crm' | 'mail_a' | 'mail_b';
export type Focus = {x: number; y: number; s: number};
export type Clip = {
  kind: 'clip'; id: string; video: Video; from: number; to: number; rate: number;
  zoomFrom: Focus; zoomTo?: Focus;
  zoomSec?: number; // camera move length in output seconds (default: the whole clip)
};
export type Gap = {kind: 'gap'; id: string; seconds: number; text: string; note: string};
export type Card = {kind: 'end'; id: string; seconds: number};
export type Item = Clip | Gap | Card;

type Take = {
  take: string; t0: number; clock: string; marks: Record<string, number>; clicks: number[];
  steps: {t: number; step: string; what: string}[]; keys: {t: number; label: string}[]; events: Record<string, number>; duration: number;
  act: number | null; // when Undo took over the screen
};
const T = data as unknown as Partial<Record<Video, Take>>;

const C: Focus = {x: 735, y: 494.5, s: 1}; // the whole screen: the edge light and the bubble are visible
const REQ: Focus = {x: 735, y: 800, s: 1.7}; // the request bubble, the only tight shot during the requests
const READ: Focus = {x: 1040, y: 520, s: 1.6}; // the email
const MAIL_TEXT: Focus = {x: 735, y: 570, s: 1.6}; // the description written by Undo, and the bubble under it

/** A clip that lasts `seconds` in the film, whatever its length in the take. */
const fit = (id: string, video: Video, from: number, to: number, seconds: number, zoomFrom: Focus, zoomTo?: Focus, zoomSec?: number): Clip =>
  ({kind: 'clip', id, video, from, to, rate: (to - from) / seconds, zoomFrom, zoomTo, zoomSec});
/** A clip at real speed: the requests, so the voice stays in sync with the live transcript. */
const live = (id: string, video: Video, from: number, to: number, zoomFrom: Focus, zoomTo?: Focus, zoomSec?: number): Clip =>
  ({kind: 'clip', id, video, from, to, rate: 1, zoomFrom, zoomTo, zoomSec});

const event = (t: Take, suffix: string) => t.events[Object.keys(t.events).find((k) => k.endsWith(suffix)) ?? ''] ?? 0;
const firstAct = (t: Take) => t.act ?? t.marks.done - 5;

const lateBy = () => {
  if (!T.mail_a || !T.mail_b) return '';
  const min = Math.round((T.mail_b.t0 - T.mail_a.t0) / 60);
  if (min < 60) return `${min} minutes later`;
  return `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, '0')} later`;
};

const blender = (t: Take): Item[] => {
  const m = t.marks;
  const del = event(t, ' Delete');
  const start = t.events.start ?? 6;
  const act = firstAct(t);
  return [
    fit('b0', 'blender', start, del - 2.2, 10.2, C),
    live('b1', 'blender', del - 2.2, del + 2.6, C),
    fit('b2', 'blender', del + 2.6, m.hotkey - 0.4, 6.6, C),
    live('b3', 'blender', m.hotkey - 0.4, m.voice_end + 0.3, C, REQ, 0.8),
    fit('b4', 'blender', m.voice_end + 0.3, m.request_sent + 0.4, 1.7, REQ),
    fit('b5', 'blender', m.request_sent + 0.4, act - 0.3, 2, REQ, C, 1.2),
    fit('b6', 'blender', act - 0.3, m.done, 9.6, C),
    live('b7', 'blender', m.done, m.done + 2.2, C),
  ];
};

const crm = (t: Take): Item[] => {
  const m = t.marks;
  const act = firstAct(t);
  return [
    fit('c0', 'crm', m.rec_start, m.form_filled + 0.4, 2.8, C),
    fit('c1', 'crm', m.form_filled + 0.4, m.login + 3, 3, C),
    live('c2', 'crm', m.hotkey - 0.4, m.voice_end + 0.3, C, REQ, 0.8),
    fit('c3', 'crm', m.voice_end + 0.3, m.request_sent + 0.4, 1.5, REQ),
    fit('c4', 'crm', m.request_sent + 0.4, act - 0.3, 1.6, REQ, C, 1),
    fit('c5', 'crm', act - 0.3, m.done, 7.4, C),
    live('c6', 'crm', m.done, m.done + 1.8, C),
  ];
};

const mailA = (t: Take): Item[] => {
  const m = t.marks;
  return [
    fit('a0', 'mail_a', m.rec_start, m.mail_open + 0.3, 1.7, C),
    fit('a1', 'mail_a', m.mail_open + 0.3, m.read, 7.2, C, READ, 1.5),
  ];
};

const mailB = (t: Take): Item[] => {
  const m = t.marks;
  const act = firstAct(t);
  return [
    {kind: 'gap', id: 'gap', seconds: 1.4, text: lateBy(), note: 'Real time between the two recordings'},
    fit('m1', 'mail_b', m.rec_start, m.hotkey - 0.4, 1.6, C),
    live('m2', 'mail_b', m.hotkey - 0.4, m.voice_end + 0.3, C, REQ, 0.8),
    fit('m3', 'mail_b', m.voice_end + 0.3, m.request_sent + 0.4, 1.4, REQ),
    fit('m4', 'mail_b', m.request_sent + 0.4, act - 0.3, 1.8, REQ, C, 1),
    fit('m5', 'mail_b', act - 0.3, m.done, 3.2, C, MAIL_TEXT, 1.6),
    {kind: 'clip', id: 'm6', video: 'mail_b', from: m.done + 1, to: m.done + 1.1, rate: 0.05, zoomFrom: MAIL_TEXT},
  ];
};

export const items: Item[] = [
  ...(T.blender ? blender(T.blender) : []),
  ...(T.crm ? crm(T.crm) : []),
  ...(T.mail_a ? mailA(T.mail_a) : []),
  ...(T.mail_b ? mailB(T.mail_b) : []),
  {kind: 'end', id: 'end', seconds: 0.3 + vo.end + 1.8},
];

// On the end card: how these takes were made.
export const disclosure = [
  'Real recordings on a Mac, sped up in places. Narration and spoken requests: ElevenLabs voices, the requests fed into Undo’s audio input.',
  'Blender: scripted scene, steps prepared in advance. CRM: demo app. Email: sample. SignalConso: real site, nothing submitted.',
];

// Voice lines: line id, clip id, offset in seconds after the clip starts. A person's line starts where the take played it.
const spoken = (t: Take | undefined) => (t ? t.marks.voice_start - (t.marks.hotkey - 0.4) : 0);
export const voCues: {id: keyof typeof vo; clip: string; at: number; user?: boolean}[] = ([
  {id: 'intro', clip: 'b0', at: 0.3},
  {id: 'bl1', clip: 'b1', at: 0.1},
  {id: 'bl2', clip: 'b2', at: 0.1},
  {id: 'bl_req', clip: 'b3', at: spoken(T.blender), user: true},
  {id: 'bl3', clip: 'b6', at: 0.2},
  {id: 'crm1', clip: 'c0', at: 0.2},
  {id: 'crm_req', clip: 'c2', at: spoken(T.crm), user: true},
  {id: 'crm2', clip: 'c5', at: 0.1},
  {id: 'mail1', clip: 'a0', at: 0.3},
  {id: 'mail_req', clip: 'm2', at: spoken(T.mail_b), user: true},
  {id: 'mail2', clip: 'm4', at: 0.3},
  {id: 'end', clip: 'end', at: 0.3},
] as {id: keyof typeof vo; clip: string; at: number; user?: boolean}[]).filter((c) => items.some((i) => i.id === c.clip));

export const voText: Record<keyof typeof vo, string> = {
  intro: '⌘Z goes back one step at a time, inside one app. Undo keeps a history of what happened on your Mac, and can act on it. Three real takes.',
  bl1: 'Say you don’t really know Blender. You delete the pool and the deck by mistake, and you keep working.',
  bl2: '⌘Z would bring them back, but erase everything since. An expert knows a way around that. Most of us don’t.',
  bl_req: 'No, no, no… I deleted the pool and the deck earlier, and I don’t know how to get them back. Put them back, without losing anything I’ve done since.',
  bl3: 'Undo does it for you. It steps back, copies the pool and the deck, returns to the present, and pastes them in. Nothing is lost.',
  crm1: 'A visit report, filled in. The session expires, and the form comes back empty.',
  crm_req: 'Oh no… the session expired and my visit report is gone. Put back what I’d filled in.',
  crm2: 'Undo finds the last state of the form in its history, and fills in every field. It stops before saving.',
  mail1: 'It doesn’t have to be a mistake. This morning, you checked a delivery email. Now there’s a complaint to file, and the details are back in that email.',
  mail_req: 'In the description, explain that my order never arrived, with the order number, the date, the item, the amount and the package tracking from the email I read this morning.',
  mail2: 'Undo finds that email in its history and writes the description. Nothing gets sent.',
  end: 'Two taps on Shift to ask, Esc to stop at any time. Undo runs on Holo, by H Company.',
};
export const voDur = vo as Record<string, number>;

// ---- per-take events, in source seconds ----------------------------------------------------------------------------
type Key = {t: number; label: string; repeat?: number; every?: number; count?: number; total?: number};
/** Keys of the take, with their rank in a run of the same key (⌘Z × 3). */
const keysOf = (t: Take): Key[] => {
  const keys: Key[] = [{t: t.marks.hotkey, label: '⇧ ⇧'}, {t: t.marks.request_sent, label: 'Enter'}, ...t.keys].sort((a, b) => a.t - b.t);
  return keys.map((k, i) => {
    let a = i;
    let b = i;
    while (a > 0 && keys[a - 1].label === k.label) a--;
    while (b < keys.length - 1 && keys[b + 1].label === k.label) b++;
    return {...k, count: i - a + 1, total: b - a + 1};
  });
};

type TakeNotes = {
  clicks: number[]; agentClicks: number[];
  typing: {from: number; to: number; who: 'user' | 'agent'}[];
  keys: Key[];
  masks?: {x: number; y: number; w: number; h: number; color: string}[]; // personal account names in Mail's sidebar
};

const notes = (t: Take | undefined, extra: Partial<TakeNotes> = {}): TakeNotes | null => t ? {
  clicks: t.clicks ?? [], agentClicks: [], keys: t.marks.hotkey ? keysOf(t) : [], typing: [], ...extra,
} : null;

const agentTyping = (t: Take | undefined) => (t ? [{from: firstAct(t), to: t.marks.done, who: 'agent' as const}] : []);

export const takes = Object.fromEntries(Object.entries({
  blender: notes(T.blender),
  crm: notes(T.crm, {typing: agentTyping(T.crm)}),
  mail_a: notes(T.mail_a, {
    masks: [{x: 20, y: 415, w: 100, h: 18, color: '#191b1c'}, {x: 20, y: 735, w: 100, h: 18, color: '#191b1c'}],
  }),
  mail_b: notes(T.mail_b, {typing: agentTyping(T.mail_b)}),
}).filter(([, v]) => v)) as Record<Video, TakeNotes>;

// ---- derived timing -------------------------------------------------------
export const itemSeconds = (it: Item) => (it.kind === 'clip' ? (it.to - it.from) / it.rate : it.seconds);
export const itemFrames = (it: Item) => Math.round(itemSeconds(it) * FPS);

export const starts: Record<string, number> = {};
let acc = 0;
for (const it of items) {
  starts[it.id] = acc;
  acc += itemFrames(it);
}
export const TOTAL_FRAMES = acc;

/** Output frame at which a source time of a take is shown, or null when it is cut. */
export const srcToFrame = (video: Video, s: number): number | null => {
  for (const it of items) {
    if (it.kind !== 'clip' || it.video !== video) continue;
    if (s >= it.from && s < it.to) return starts[it.id] + Math.round(((s - it.from) / it.rate) * FPS);
  }
  return null;
};

/** Output frame ranges covering a source range (one per clip it overlaps), with the clip rate. */
export const srcRangeToFrames = (video: Video, a: number, b: number) => {
  const out: {start: number; frames: number; rate: number}[] = [];
  for (const it of items) {
    if (it.kind !== 'clip' || it.video !== video) continue;
    const lo = Math.max(a, it.from);
    const hi = Math.min(b, it.to);
    if (hi <= lo) continue;
    out.push({
      start: starts[it.id] + Math.round(((lo - it.from) / it.rate) * FPS),
      frames: Math.max(1, Math.round(((hi - lo) / it.rate) * FPS)),
      rate: it.rate,
    });
  }
  return out;
};
