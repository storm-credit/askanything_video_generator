import React from 'react';
import { Composition, getInputProps } from 'remotion';
import { Main } from './Main';

export const RemotionRoot: React.FC = () => {
    const inputProps = getInputProps() as Record<string, unknown> || {};
    const cuts = (Array.isArray(inputProps.cuts) ? inputProps.cuts : []) as React.ComponentProps<typeof Main>['cuts'];
    const totalFrames = (typeof inputProps.totalDurationInFrames === 'number' ? inputProps.totalDurationInFrames : 150);
    const introImagePath = typeof inputProps.introImagePath === 'string' ? inputProps.introImagePath : undefined;
    const outroImagePath = typeof inputProps.outroImagePath === 'string' ? inputProps.outroImagePath : undefined;
    const title = typeof inputProps.title === 'string' ? inputProps.title : undefined;
    const bgmPath = typeof inputProps.bgmPath === 'string' ? inputProps.bgmPath : undefined;
    const cameraStyle = (typeof inputProps.cameraStyle === 'string' ? inputProps.cameraStyle : 'auto') as 'auto' | 'dynamic' | 'gentle' | 'static';
    const captionSize = typeof inputProps.captionSize === 'number' ? inputProps.captionSize : 48;
    const captionY = typeof inputProps.captionY === 'number' ? inputProps.captionY : 28;

    return (
        <>
            <Composition
                id="Main"
                component={Main}
                durationInFrames={totalFrames}
                fps={30}
                width={1080}
                height={1920}
                defaultProps={{ cuts, introImagePath, outroImagePath, bgmPath, title, cameraStyle, captionSize, captionY }}
            />
        </>
    );
};
