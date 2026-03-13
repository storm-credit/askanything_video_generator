import { Composition, getInputProps } from 'remotion';
import { Main } from './Main';

const inputProps = getInputProps() as Record<string, unknown> || {};

export const RemotionRoot: React.FC = () => {
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
