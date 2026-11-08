import React from 'react';
import {Composition} from 'remotion';
import {Film} from './Film';
import {FPS, FRAME, TOTAL_FRAMES} from './timeline';

export const Root: React.FC = () => (
  <Composition id="Undo" component={Film} durationInFrames={TOTAL_FRAMES} fps={FPS} width={FRAME.w} height={FRAME.h} />
);
