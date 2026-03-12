import os
import json

def scaffold_remotion():
    base_dir = "remotion"
    os.makedirs(base_dir, exist_ok=True)
    os.makedirs(os.path.join(base_dir, "src"), exist_ok=True)
    
    # 1. package.json
    package_json = {
        "name": "askanything-remotion",
        "version": "1.0.0",
        "description": "Remotion video renderer for AskAnything project",
        "scripts": {
            "start": "remotion studio",
            "build": "remotion render src/index.ts Main out/video.mp4",
            "upgrade": "remotion upgrade"
        },
        "dependencies": {
            "remotion": "^4.0.0",
            "react": "^18.0.0",
            "react-dom": "^18.0.0"
        },
        "devDependencies": {
            "@remotion/cli": "^4.0.0",
            "@remotion/eslint-config": "^4.0.0",
            "@types/react": "^18.0.0",
            "prettier": "^2.0.0",
            "typescript": "^5.0.0"
        }
    }
    with open(os.path.join(base_dir, "package.json"), "w") as f:
        json.dump(package_json, f, indent=2)

    # 2. remotion.config.ts
    remotion_config = """import { Config } from '@remotion/cli/config';
Config.setVideoImageFormat('jpeg');
"""
    with open(os.path.join(base_dir, "remotion.config.ts"), "w") as f:
        f.write(remotion_config)

    # 3. tsconfig.json
    tsconfig = {
        "compilerOptions": {
            "jsx": "react-jsx",
            "allowJs": True,
            "skipLibCheck": True,
            "esModuleInterop": True,
            "allowSyntheticDefaultImports": True,
            "strict": False,
            "forceConsistentCasingInFileNames": True,
            "noFallthroughCasesInSwitch": True,
            "module": "esnext",
            "moduleResolution": "node",
            "resolveJsonModule": True,
            "isolatedModules": True,
            "noEmit": True
        },
        "include": ["src"]
    }
    with open(os.path.join(base_dir, "tsconfig.json"), "w") as f:
        json.dump(tsconfig, f, indent=2)

    # 4. src/index.ts
    index_ts = """import { registerRoot } from 'remotion';
import { RemotionRoot } from './Root';

registerRoot(RemotionRoot);
"""
    with open(os.path.join(base_dir, "src", "index.ts"), "w") as f:
        f.write(index_ts)

    # 5. src/Root.tsx
    root_tsx = """import { Composition } from 'remotion';
import { Main } from './Main';

export const RemotionRoot: React.FC = () => {
    return (
        <>
            <Composition
                id="Main"
                component={Main}
                durationInFrames={150}
                fps={30}
                width={1080}
                height={1920}
            />
        </>
    );
};
"""
    with open(os.path.join(base_dir, "src", "Root.tsx"), "w") as f:
        f.write(root_tsx)

    # 6. src/Main.tsx
    main_tsx = """import { AbsoluteFill } from 'remotion';

export const Main: React.FC = () => {
    return (
        <AbsoluteFill style={{ backgroundColor: 'black', justifyContent: 'center', alignItems: 'center' }}>
            <h1 style={{ color: 'white', fontSize: 100 }}>AskAnything Video Generator</h1>
        </AbsoluteFill>
    );
};
"""
    with open(os.path.join(base_dir, "src", "Main.tsx"), "w") as f:
        f.write(main_tsx)

    print("Remotion scaffolding completed.")

if __name__ == "__main__":
    scaffold_remotion()
