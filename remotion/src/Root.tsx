import { Composition, getInputProps } from 'remotion';
import { Main } from './Main';

const inputProps = getInputProps() || { cuts: [], totalDurationInFrames: 150 };

export const RemotionRoot: React.FC = () => {
    const cuts = inputProps.cuts || [];
    const totalFrames = inputProps.totalDurationInFrames || 150;

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
