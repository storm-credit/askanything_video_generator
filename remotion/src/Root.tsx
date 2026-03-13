import React from 'react';
import { Composition, getInputProps } from 'remotion';
import { Main } from './Main';

export const RemotionRoot: React.FC = () => {
    const inputProps = getInputProps() as Record<string, unknown> || {};
    const cuts = (Array.isArray(inputProps.cuts) ? inputProps.cuts : []) as React.ComponentProps<typeof Main>['cuts'];
    const totalFrames = (typeof inputProps.totalDurationInFrames === 'number' ? inputProps.totalDurationInFrames : 150);

    return (
        <>
            <Composition
                id="Main"
                component={Main}
                durationInFrames={totalFrames}
                fps={24}
                width={1080}
                height={1920}
                defaultProps={{ cuts }}
            />
        </>
    );
};
