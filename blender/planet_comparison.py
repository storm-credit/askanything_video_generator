"""행성 크기 비교 영상 자동 생성 — Blender Python.

Blender 커맨드라인으로 실행:
  blender --background --python planet_comparison.py

출력: 9:16 세로 영상 (1080x1920), 카메라 줌아웃 애니메이션
"""
import bpy
import math
import os
import sys

# ── 설정 ──
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 9:16 세로 (YouTube Shorts)
RESOLUTION_X = 1080
RESOLUTION_Y = 1920
FPS = 24
TOTAL_FRAMES = 240  # 10초

# ── 행성 데이터 (실제 크기 비율) ──
PLANET_DATA = {
    "solar_system": {
        "title": "태양계 크기 비교",
        "planets": [
            {"name": "Moon",    "radius": 0.27, "color": (0.7, 0.7, 0.7, 1)},
            {"name": "Earth",   "radius": 1.0,  "color": (0.2, 0.4, 0.8, 1)},
            {"name": "Neptune", "radius": 3.88, "color": (0.3, 0.3, 0.9, 1)},
            {"name": "Jupiter", "radius": 11.2, "color": (0.8, 0.6, 0.3, 1)},
            {"name": "Sun",     "radius": 109.0, "color": (1.0, 0.8, 0.2, 1)},
        ],
    },
    "giant_stars": {
        "title": "별 크기 비교",
        "planets": [
            {"name": "Earth",       "radius": 0.009,  "color": (0.2, 0.4, 0.8, 1)},
            {"name": "Sun",         "radius": 1.0,    "color": (1.0, 0.8, 0.2, 1)},
            {"name": "Sirius",      "radius": 1.71,   "color": (0.9, 0.9, 1.0, 1)},
            {"name": "Arcturus",    "radius": 25.4,   "color": (1.0, 0.5, 0.2, 1)},
            {"name": "Betelgeuse", "radius": 764.0,  "color": (1.0, 0.3, 0.1, 1)},
            {"name": "UY Scuti",   "radius": 1708.0, "color": (1.0, 0.2, 0.1, 1)},
        ],
    },
}


def clear_scene():
    """씬 초기화."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    # 기존 컬렉션의 모든 오브젝트 제거
    for obj in bpy.data.objects:
        bpy.data.objects.remove(obj)


def create_space_background():
    """우주 배경 (검정)."""
    world = bpy.context.scene.world
    if not world:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.0, 0.0, 0.02, 1)  # 거의 검정
    bg.inputs[1].default_value = 1.0


def create_planet(name, radius, color, position):
    """행성 구체 생성."""
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=radius,
        segments=64,
        ring_count=32,
        location=position,
    )
    obj = bpy.context.active_object
    obj.name = name

    # 머티리얼
    mat = bpy.data.materials.new(name=f"mat_{name}")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.8

    # 발광 효과 (별인 경우)
    if radius > 10:
        bsdf.inputs["Emission Color"].default_value = color
        bsdf.inputs["Emission Strength"].default_value = 2.0

    obj.data.materials.append(mat)
    return obj


def setup_camera_animation(planets, total_frames):
    """카메라 줌아웃 애니메이션 — 작은 것부터 큰 것까지."""
    # 카메라 생성
    bpy.ops.object.camera_add(location=(0, -5, 0))
    cam = bpy.context.active_object
    cam.name = "Camera"
    bpy.context.scene.camera = cam

    # 카메라가 원점을 바라보도록
    cam.rotation_euler = (math.radians(90), 0, 0)

    # 가장 큰 행성까지 줌아웃
    max_radius = max(p["radius"] for p in planets)
    start_dist = planets[0]["radius"] * 5  # 가장 작은 것 가까이
    end_dist = max_radius * 3  # 가장 큰 것 멀리

    # 키프레임 — Y축으로 뒤로 이동
    cam.location = (0, -start_dist, 0)
    cam.keyframe_insert(data_path="location", frame=1)

    cam.location = (0, -end_dist, 0)
    cam.keyframe_insert(data_path="location", frame=total_frames)

    # 부드러운 이동
    for fc in cam.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
            kp.easing = 'EASE_IN_OUT'

    return cam


def setup_lighting():
    """조명 설정."""
    # 키 라이트
    bpy.ops.object.light_add(type='SUN', location=(10, -10, 10))
    light = bpy.context.active_object
    light.data.energy = 3.0

    # 림 라이트
    bpy.ops.object.light_add(type='POINT', location=(-5, -5, 5))
    rim = bpy.context.active_object
    rim.data.energy = 500


def render_comparison(preset_name, output_filename=None):
    """행성 비교 영상 렌더링."""
    preset = PLANET_DATA.get(preset_name)
    if not preset:
        print(f"프리셋 '{preset_name}' 없음")
        return

    clear_scene()
    create_space_background()
    setup_lighting()

    planets = preset["planets"]

    # 행성 배치 — 왼쪽에서 오른쪽으로, 크기순
    x_offset = 0
    for i, p in enumerate(planets):
        # 정규화 — 가장 큰 행성 기준 스케일
        scale_factor = 1.0
        if planets[-1]["radius"] > 100:
            scale_factor = 10.0 / planets[-1]["radius"]

        r = p["radius"] * scale_factor
        x_offset += r + 0.5  # 이전 행성 옆에 배치
        position = (x_offset, 0, 0)
        create_planet(p["name"], r, tuple(p["color"]), position)
        x_offset += r + 0.5

    # 카메라 애니메이션
    setup_camera_animation(planets, TOTAL_FRAMES)

    # 렌더 설정
    scene = bpy.context.scene
    scene.render.resolution_x = RESOLUTION_X
    scene.render.resolution_y = RESOLUTION_Y
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = TOTAL_FRAMES
    scene.render.engine = 'BLENDER_EEVEE_NEXT'  # 빠른 렌더링
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'

    # 출력 경로
    filename = output_filename or f"{preset_name}_comparison.mp4"
    scene.render.filepath = os.path.join(OUTPUT_DIR, filename)

    # 렌더링
    print(f"[Blender] 렌더링 시작: {preset_name} ({TOTAL_FRAMES} frames)")
    bpy.ops.render.render(animation=True)
    print(f"OK [Blender] 렌더링 완료: {scene.render.filepath}")

    return scene.render.filepath


# 실행
if __name__ == "__main__":
    # 커맨드라인 인자로 프리셋 선택
    preset = "solar_system"
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1:]
        if args:
            preset = args[0]

    render_comparison(preset)
