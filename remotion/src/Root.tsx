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

    return (
        <>
            <Composition
                id="Main"
                component={Main}
                durationInFrames={totalFrames}
                fps={24}
                width={1080}
                height={1920}
                defaultProps={{ cuts, introImagePath, outroImagePath, bgmPath, title }}
            />
        </>
    );
};
