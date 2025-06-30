import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from matplotlib.colors import LinearSegmentedColormap
import matplotlib as mpl
import heapq
from collections import deque
import itertools

# 폰트 설정 (한글 표시)
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

# ===== 지형 특성 관련 상수 =====
FEATURE_NONE = 0
FEATURE_TRAP = 2          # 함정
FEATURE_SECRET_HINT = 2   # 비밀 통로 힌트
FEATURE_OBSTACLE = 3      # 장애물 (복도)
FEATURE_BRIDGE = 4        # 다리
FEATURE_ENTRANCE = 5      # 입구
FEATURE_EXIT = 6          # 출구
FEATURE_PATH = 7          # 주 경로
FEATURE_TREASURE = 8      # 보물
FEATURE_MONSTER_WEAK = FEATURE_ENTRANCE/2     # 약한 몬스터
FEATURE_MONSTER_NORMAL = FEATURE_BRIDGE  # 일반 몬스터
FEATURE_MONSTER_STRONG = FEATURE_TREASURE/2  # 강한 몬스터
FEATURE_MONSTER_BOSS = 1    # 보스 몬스터

# 특성 이름 매핑
FEATURE_NAMES = {
    FEATURE_NONE: "일반",
    FEATURE_TRAP: "함정",
    FEATURE_SECRET_HINT: "비밀통로 힌트",
    FEATURE_OBSTACLE: "장애물",
    FEATURE_BRIDGE: "다리",
    FEATURE_ENTRANCE: "입구",
    FEATURE_EXIT: "출구", 
    FEATURE_PATH: "주경로",
    FEATURE_TREASURE: "보물",
    FEATURE_MONSTER_WEAK: "약한 몬스터",
    FEATURE_MONSTER_NORMAL: "일반 몬스터",
    FEATURE_MONSTER_STRONG: "강한 몬스터",
    FEATURE_MONSTER_BOSS: "보스 몬스터"
}

# 몬스터 타입 정의
MONSTER_TYPES = {
    FEATURE_MONSTER_WEAK: {
        "names": ["고블린", "박쥐", "쥐", "슬라임", "스켈레톤"],
        "level_range": (1, 3),
        "hp_range": (5, 15),
        "attack_range": (1, 4),
        "symbol": "m",
        "description": "초보 모험가도 처치할 수 있는 약한 몬스터"
    },
    FEATURE_MONSTER_NORMAL: {
        "names": ["오크", "울프", "거미", "좀비", "코볼트"],
        "level_range": (3, 6),
        "hp_range": (15, 35),
        "attack_range": (3, 8),
        "symbol": "M",
        "description": "적당한 실력이 필요한 일반 몬스터"
    },
    FEATURE_MONSTER_STRONG: {
        "names": ["오거", "트롤", "미노타우로스", "가고일", "리치"],
        "level_range": (6, 10),
        "hp_range": (35, 70),
        "attack_range": (8, 15),
        "symbol": "S",
        "description": "강력한 실력이 필요한 위험한 몬스터"
    },
    FEATURE_MONSTER_BOSS: {
        "names": ["드래곤", "데몬 로드", "리치 킹", "고대 골렘", "밤의 여왕"],
        "level_range": (10, 15),
        "hp_range": (70, 150),
        "attack_range": (15, 25),
        "symbol": "B",
        "description": "던전의 주인으로 극도로 위험한 보스급 몬스터"
    }
}

# ===========================

# 던전과 높이 맵 생성 함수
def generate_dungeon(width, height, room_count=8, room_min=8, room_max=15, min_room_distance=4, corridor_width_options=[1, 2], extra_connection_prob=0.3):
    # ... (map7.py와 동일) ...
    dungeon = np.zeros((height, width), dtype=int)
    rooms = []
    attempts = 0
    max_attempts = 200
    while len(rooms) < room_count and attempts < max_attempts:
        w = np.random.randint(room_min, room_max)
        h = np.random.randint(room_min, room_max)
        x = np.random.randint(1, width - w - 1)
        y = np.random.randint(1, height - h - 1)
        new_room_rect = (x, y, w, h)
        too_close = False
        for rx, ry, rw, rh in rooms:
            if not (x + w + min_room_distance <= rx or rx + rw + min_room_distance <= x or
                   y + h + min_room_distance <= ry or ry + rh + min_room_distance <= y):
                too_close = True; break
        attempts += 1
        if too_close: continue
        dungeon[y:y+h, x:x+w] = 1
        rooms.append(new_room_rect)
    if len(rooms) < 2: print("방 부족"); return dungeon, rooms, []
    connected = {0}; edges = []; room_centers = [(r[0] + r[2]//2, r[1] + r[3]//2) for r in rooms]
    for i in range(len(rooms)): 
        for j in range(i + 1, len(rooms)): 
            dist = abs(room_centers[i][0] - room_centers[j][0]) + abs(room_centers[i][1] - room_centers[j][1])
            edges.append((dist, i, j))
    edges.sort(); corridors = []; mst_edges_count = 0
    for dist, i, j in edges:
        if len(connected) == len(rooms): break
        if i in connected and j not in connected or i not in connected and j in connected:
            connected.add(i); connected.add(j)
            x1, y1 = room_centers[i]; x2, y2 = room_centers[j]
            corridor_width = np.random.choice(corridor_width_options)
            points = create_corridor(dungeon, x1, y1, x2, y2, corridor_width)
            if points: corridors.append(points)
            mst_edges_count += 1
    remaining_edges = edges[mst_edges_count:]; np.random.shuffle(remaining_edges)
    num_extra_connections = int(len(remaining_edges) * extra_connection_prob)
    for k in range(min(num_extra_connections, len(remaining_edges))):
        dist, i, j = remaining_edges[k]
        x1, y1 = room_centers[i]; x2, y2 = room_centers[j]
        # print(f"곁가지 복도 시도: 방 {i} <-> 방 {j}") # 로그 출력 줄임
        corridor_width = np.random.choice(corridor_width_options)
        points = create_corridor(dungeon, x1, y1, x2, y2, corridor_width)
        if points: corridors.append(points)
    return dungeon, rooms, corridors

def create_corridor(dungeon, x1, y1, x2, y2, width):
    # ... (map7.py와 동일) ...
    height, map_width = dungeon.shape; points = []
    if np.random.rand() < 0.7:
        if np.random.rand() < 0.5:
            for cy in range(min(y1, y2), max(y1, y2) + 1): 
                for offset in range(width): px=x1+offset; 
                if 0<=px<map_width and 0<=cy<height: dungeon[cy, px]=1; points.append((cy, px))
            for cx in range(min(x1, x2), max(x1, x2) + 1): 
                for offset in range(width): py=y2+offset; 
                if 0<=py<height and 0<=cx<map_width: dungeon[py, cx]=1; points.append((py, cx))
        else:
            for cx in range(min(x1, x2), max(x1, x2) + 1): 
                for offset in range(width): py=y1+offset; 
                if 0<=py<height and 0<=cx<map_width: dungeon[py, cx]=1; points.append((py, cx))
            for cy in range(min(y1, y2), max(y1, y2) + 1): 
                for offset in range(width): px=x2+offset; 
                if 0<=px<map_width and 0<=cy<height: dungeon[cy, px]=1; points.append((cy, px))
    else:
        mid_x = np.random.randint(min(x1,x2), max(x1,x2)+1) if x1!=x2 else x1
        mid_y = np.random.randint(min(y1,y2), max(y1,y2)+1) if y1!=y2 else y1
        for cy in range(min(y1, mid_y), max(y1, mid_y)+1): 
            for offset in range(width): px=x1+offset; 
            if 0<=px<map_width and 0<=cy<height: dungeon[cy, px]=1; points.append((cy, px))
        for cx in range(min(x1, mid_x), max(x1, mid_x)+1): 
            for offset in range(width): py=mid_y+offset; 
            if 0<=py<height and 0<=cx<map_width: dungeon[py, cx]=1; points.append((py, cx))
        for cy in range(min(mid_y, y2), max(mid_y, y2)+1): 
            for offset in range(width): px=mid_x+offset; 
            if 0<=px<map_width and 0<=cy<height: dungeon[cy, px]=1; points.append((cy, px))
        for cx in range(min(mid_x, x2), max(mid_x, x2)+1): 
            for offset in range(width): py=y2+offset; 
            if 0<=py<height and 0<=cx<map_width: dungeon[py, cx]=1; points.append((py, cx))
    return list(set(points))

def generate_monsters(dungeon, rooms, feature_map, entrance, exit_coords, 
                     monster_density=0.15, boss_room_prob=0.7):
    """몬스터를 던전에 배치하는 함수"""
    import random
    
    height, width = dungeon.shape
    monsters = []  # 몬스터 상세 정보 저장
    
    # 입구/출구 근처는 몬스터 배치 금지 구역
    safe_zone_radius = 3
    
    def is_safe_zone(y, x):
        if entrance and abs(y - entrance[0]) <= safe_zone_radius and abs(x - entrance[1]) <= safe_zone_radius:
            return True
        if exit_coords and abs(y - exit_coords[0]) <= safe_zone_radius and abs(x - exit_coords[1]) <= safe_zone_radius:
            return True
        return False
    
    def create_monster(monster_type, y, x):
        """몬스터 개체 생성"""
        monster_info = MONSTER_TYPES[monster_type]
        level = random.randint(*monster_info["level_range"])
        hp = random.randint(*monster_info["hp_range"])
        attack = random.randint(*monster_info["attack_range"])
        name = random.choice(monster_info["names"])
        
        return {
            "name": name,
            "type": FEATURE_NAMES[monster_type],
            "level": level,
            "hp": hp,
            "attack": attack,
            "position": [x, y],
            "symbol": monster_info["symbol"],
            "description": monster_info["description"]
        }
    
    # 1. 각 방에 몬스터 배치
    for i, (rx, ry, rw, rh) in enumerate(rooms):
        room_area = rw * rh
        # 방 크기에 따른 몬스터 수 결정
        monster_count = max(1, int(room_area * monster_density / 20))
        
        # 보스 몬스터가 나올 확률
        has_boss = random.random() < boss_room_prob and room_area > 100
        
        placed_count = 0
        attempts = 0
        
        while placed_count < monster_count and attempts < 50:
            x = random.randint(rx + 1, rx + rw - 2) if rw > 2 else rx
            y = random.randint(ry + 1, ry + rh - 2) if rh > 2 else ry
            
            # 이미 특성이 있는 곳이거나 안전구역이면 스킵
            if (feature_map[y, x] != FEATURE_NONE and feature_map[y, x] != FEATURE_PATH) or is_safe_zone(y, x):
                attempts += 1
                continue
            
            # 몬스터 타입 결정
            if has_boss and placed_count == 0:
                monster_type = FEATURE_MONSTER_BOSS
                has_boss = False  # 보스는 방당 하나만
            elif room_area > 150:  # 큰 방
                weights = [0.2, 0.4, 0.3, 0.1]  # 약함, 보통, 강함, 보스
                monster_type = random.choices([
                    FEATURE_MONSTER_WEAK, FEATURE_MONSTER_NORMAL, 
                    FEATURE_MONSTER_STRONG, FEATURE_MONSTER_BOSS
                ], weights=weights)[0]
            elif room_area > 100:  # 중간 방
                weights = [0.3, 0.5, 0.2, 0]
                monster_type = random.choices([
                    FEATURE_MONSTER_WEAK, FEATURE_MONSTER_NORMAL, 
                    FEATURE_MONSTER_STRONG, FEATURE_MONSTER_BOSS
                ], weights=weights)[0]
            else:  # 작은 방
                weights = [0.6, 0.4, 0, 0]
                monster_type = random.choices([
                    FEATURE_MONSTER_WEAK, FEATURE_MONSTER_NORMAL, 
                    FEATURE_MONSTER_STRONG, FEATURE_MONSTER_BOSS
                ], weights=weights)[0]
            
            # 보물 근처면 강한 몬스터 배치 확률 증가
            treasure_nearby = False
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    ny, nx = y + dy, x + dx
                    if (0 <= ny < height and 0 <= nx < width and 
                        feature_map[ny, nx] == FEATURE_TREASURE):
                        treasure_nearby = True
                        break
                if treasure_nearby:
                    break
            
            if treasure_nearby and random.random() < 0.7:
                monster_type = random.choice([FEATURE_MONSTER_STRONG, FEATURE_MONSTER_BOSS])
            
            feature_map[y, x] = monster_type
            monster = create_monster(monster_type, y, x)
            monsters.append(monster)
            placed_count += 1
            attempts += 1
    
    # 2. 복도에 가끔 몬스터 배치 (낮은 확률)
    corridor_monster_prob = 0.05
    for y in range(height):
        for x in range(width):
            if (dungeon[y, x] == 1 and feature_map[y, x] == FEATURE_NONE and 
                not is_safe_zone(y, x) and random.random() < corridor_monster_prob):
                
                # 복도는 주로 약한 몬스터
                weights = [0.7, 0.3, 0, 0]
                monster_type = random.choices([
                    FEATURE_MONSTER_WEAK, FEATURE_MONSTER_NORMAL, 
                    FEATURE_MONSTER_STRONG, FEATURE_MONSTER_BOSS
                ], weights=weights)[0]
                
                feature_map[y, x] = monster_type
                monster = create_monster(monster_type, y, x)
                monsters.append(monster)
    
    return monsters

def generate_height_map(dungeon, rooms, corridors, smoothness=3, max_height=15, 
                        corridor_height_range=(1, 4), obstacle_prob=0.05, obstacle_height_range=(1, 3),
                        trap_prob_base = 0.015, trap_prob_corridor_center=0.005, 
                        secret_hint_prob = 0.1, treasure_prob = 0.015, 
                        monster_density=0.15, boss_room_prob=0.7):
    # ... (map7.py와 동일, 함정 확률 분리 유지) ...
    height, width = dungeon.shape
    noise = np.random.rand(height, width)
    for _ in range(smoothness): noise = (noise + np.roll(noise, 1, axis=0) + np.roll(noise, -1, axis=0) + np.roll(noise, 1, axis=1) + np.roll(noise, -1, axis=1)) / 5
    height_map = (noise * max_height).astype(int) * (dungeon == 1)
    feature_map = np.zeros_like(dungeon, dtype=int)
    room_heights = np.random.randint(1, max_height + 1, size=len(rooms))
    for i, (x, y, w, h) in enumerate(rooms):
        base_height = room_heights[i]
        for ry in range(y, y + h): 
            for rx in range(x, x + w):
                if dungeon[ry, rx] == 1:
                    is_edge = rx == x or rx == x + w - 1 or ry == y or ry == y + h - 1
                    height_map[ry, rx] = max(1, base_height + (np.random.randint(-1, 2) if is_edge else np.random.randint(-1, 1)))
    all_corridor_points = set(itertools.chain(*corridors)) if corridors else set()
    for r in range(height): 
        for c in range(width):
            if dungeon[r, c] == 1 and (r, c) in all_corridor_points:
                 is_in_room_interior = any(rx < c < rx + rw - 1 and ry < r < ry + rh - 1 for rx, ry, rw, rh in rooms)
                 if not is_in_room_interior:
                    if height_map[r, c] == 0: height_map[r, c] = np.random.randint(corridor_height_range[0], corridor_height_range[1] + 1)
                    else: height_map[r, c] = max(corridor_height_range[0], min(corridor_height_range[1], height_map[r, c]))
                    if np.random.rand() < obstacle_prob:
                         is_surrounded = all(0 <= r+dr < height and 0 <= c+dc < width and dungeon[r+dr, c+dc] == 1 and (r+dr, c+dc) in all_corridor_points for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)])
                         if is_surrounded: height_map[r, c] += np.random.randint(obstacle_height_range[0], obstacle_height_range[1] + 1); feature_map[r, c] = FEATURE_OBSTACLE
                    elif feature_map[r, c] == FEATURE_NONE:
                        h_neighbors = (dungeon[r, c-1]==1) + (dungeon[r, c+1]==1) if 0<c<width-1 else 0
                        v_neighbors = (dungeon[r-1, c]==1) + (dungeon[r+1, c]==1) if 0<r<height-1 else 0
                        is_narrow = (h_neighbors + v_neighbors == 2 and h_neighbors != 1)
                        if is_narrow:
                             below_empty = (r + 1 < height and dungeon[r+1, c] == 0)
                             below_far = (r + 1 < height and dungeon[r+1, c] == 1 and height_map[r, c] - height_map[r+1, c] > 5)
                             if below_empty or below_far: feature_map[r, c] = FEATURE_BRIDGE
    for i, (x, y, w, h) in enumerate(rooms):
        for ry in range(y + 1, y + h - 1): 
            for rx in range(x + 1, x + w - 1):
                if dungeon[ry, rx] == 1 and feature_map[ry, rx] == FEATURE_NONE:
                    if np.random.rand() < treasure_prob: feature_map[ry, rx] = FEATURE_TREASURE
    all_dungeon_points = np.argwhere(dungeon == 1)
    for y, x in all_dungeon_points:
        if feature_map[y, x] != FEATURE_NONE: continue
        live_neighbors = 0; is_on_edge = False
        for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
            ny,nx=y+dy,x+dx
            if not(0<=ny<height and 0<=nx<width and dungeon[ny,nx]==1):
                is_on_edge=True
            else:
                live_neighbors+=1
        if not is_on_edge:
            has_diagonal_wall = any(not(0<=y+dy<height and 0<=x+dx<width and dungeon[y+dy,x+dx]==1) for dy,dx in [(-1,-1),(-1,1),(1,-1),(1,1)])
            if has_diagonal_wall:
                is_on_edge=True
        if live_neighbors == 1:
             if np.random.rand() < secret_hint_prob: feature_map[y, x] = FEATURE_SECRET_HINT
        elif live_neighbors >= 2:
            current_trap_prob = trap_prob_corridor_center if live_neighbors == 2 and not is_on_edge else trap_prob_base
            if np.random.rand() < current_trap_prob: feature_map[y, x] = FEATURE_TRAP
    height_map = np.maximum(height_map, 1) * (dungeon == 1)
    return height_map, feature_map

def select_entrance_exit(dungeon, rooms, height_map, feature_map):
    """가장 먼 두 방을 찾아 입구와 출구 선택"""
    if not rooms or len(rooms) < 2:
        print("방이 부족하여 입/출구를 제대로 설정할 수 없습니다.")
        # 임시 처리: 첫 번째 방에 입/출구 설정 (또는 오류 반환)
        if rooms:
            room = rooms[0]
            x, y, w, h = room
            ex = x + w // 2; ey = y + h // 2
            feature_map[ey, ex] = FEATURE_ENTRANCE
            feature_map[ey, ex+1] = FEATURE_EXIT # 바로 옆에 임시 출구
            height_map[ey,ex] = max(1, height_map[ey,ex])
            height_map[ey,ex+1] = 1
            return (ey, ex), (ey, ex+1)
        else:
            return None, None

    # 방 중심 좌표 계산
    room_centers = [(r[0] + r[2]//2, r[1] + r[3]//2) for r in rooms]
    
    # 가장 먼 두 방 찾기 (맨해튼 거리 기준)
    max_dist = -1
    farthest_pair = (0, 1) # 기본값
    for i in range(len(rooms)):
        for j in range(i + 1, len(rooms)):
            dist = abs(room_centers[i][0] - room_centers[j][0]) + abs(room_centers[i][1] - room_centers[j][1])
            if dist > max_dist:
                max_dist = dist
                farthest_pair = (i, j)
                
    entrance_room_idx, exit_room_idx = farthest_pair
    entrance_room = rooms[entrance_room_idx]
    exit_room = rooms[exit_room_idx]
    print(f"가장 먼 방 쌍 선택: {entrance_room_idx} <-> {exit_room_idx} (거리: {max_dist})")

    # 선택된 방 내부에 랜덤 위치 선정
    ex, ey, ew, eh = entrance_room
    entrance_x = np.random.randint(ex + 1, ex + ew - 1) if ew > 2 else ex
    entrance_y = np.random.randint(ey + 1, ey + eh - 1) if eh > 2 else ey
    
    xx, xy, xw, xh = exit_room
    exit_x = np.random.randint(xx + 1, xx + xw - 1) if xw > 2 else xx
    exit_y = np.random.randint(xy + 1, xy + xh - 1) if xh > 2 else xy

    # 입구/출구 타일이 같아지는 예외 처리 (만약 같은 방이 가장 멀리 선택될 경우 - 거의 불가능)
    if entrance_room_idx == exit_room_idx:
         while entrance_x == exit_x and entrance_y == exit_y:
            if xw > 2: exit_x = np.random.randint(xx + 1, xx + xw - 1)
            if xh > 2: exit_y = np.random.randint(xy + 1, xy + xh - 1)
            # If still same (e.g., 1x2 or 2x1 room), break loop - unavoidable
            if (xw <= 2 or xh <=2) and (entrance_x == exit_x and entrance_y == exit_y):
                break
                
    entrance = (entrance_y, entrance_x)
    exit_coords = (exit_y, exit_x)

    # 높이 설정 및 특성 부여
    height_map[entrance[0], entrance[1]] = max(1, height_map[entrance[0], entrance[1]])
    height_map[exit_coords[0], exit_coords[1]] = 1 # 출구는 낮게
    feature_map[entrance[0], entrance[1]] = FEATURE_ENTRANCE
    feature_map[exit_coords[0], exit_coords[1]] = FEATURE_EXIT
    print(f"입구 ({entrance[0]}, {entrance[1]}), 출구 ({exit_coords[0]}, {exit_coords[1]}) 설정 완료")

    # 출구 주변 높이 낮추기
    for r_off in range(-1, 2): 
        for c_off in range(-1, 2):
            if r_off == 0 and c_off == 0: continue
            nr, nc = exit_coords[0] + r_off, exit_coords[1] + c_off
            if 0 <= nr < dungeon.shape[0] and 0 <= nc < dungeon.shape[1] and dungeon[nr, nc] == 1 and (nr, nc) != entrance:
                 height_map[nr, nc] = max(1, height_map[nr, nc] // 2)
                 
    return entrance, exit_coords

def find_path_bfs(dungeon, height_map, feature_map, entrance, exit_coords, max_height_diff=4):
    # ... (map7.py와 동일) ...
    if entrance is None or exit_coords is None: return None, None
    height, width = dungeon.shape; visited = np.zeros_like(dungeon, dtype=bool); parent = {}; queue = deque([(entrance[0], entrance[1])])
    if not (0 <= entrance[0] < height and 0 <= entrance[1] < width and dungeon[entrance[0], entrance[1]] == 1):
        print(f"오류: 입구 {entrance} 유효X."); q=deque([entrance]); visited_s={entrance}; new_e=None
        while q:
            y, x = q.popleft()
            if 0<=y<height and 0<=x<width and dungeon[y,x]==1: new_e=(y,x); break
            for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                 ny, nx = y+dy, x+dx
                 if (ny,nx) not in visited_s: q.append((ny,nx)); visited_s.add((ny,nx))
        if new_e: print(f"유효 입구 {new_e}로 변경."); entrance=new_e; queue=deque([entrance])
        else: print("유효 입구 못찾음."); return None, None
    visited[entrance[0], entrance[1]] = True; directions = [(-1,0),(1,0),(0,-1),(0,1)]; path_found = False
    while queue:
        y, x = queue.popleft()
        if (y, x) == exit_coords: path_found = True; break
        current_h = height_map[y,x] if height_map[y,x]>0 else 1
        for dy, dx in directions:
            ny, nx = y+dy, x+dx
            if (0<=ny<height and 0<=nx<width and dungeon[ny,nx]==1 and not visited[ny,nx]):
                next_h = height_map[ny,nx] if height_map[ny,nx]>0 else 1
                if abs(next_h-current_h) <= max_height_diff:
                    visited[ny,nx] = True
                    queue.append((ny,nx))
                    parent[(ny,nx)]=(y,x)
    if not path_found:
        problematic_points = []
        visited_coords = np.argwhere(visited & (dungeon==1))
        for y, x in visited_coords:
            current_h = height_map[y,x] if height_map[y,x]>0 else 1
            for dy, dx in directions:
                ny, nx = y+dy, x+dx
                if (0<=ny<height and 0<=nx<width and dungeon[ny,nx]==1 and not visited[ny,nx]):
                    next_h = height_map[ny,nx] if height_map[ny,nx]>0 else 1
                    if abs(next_h-current_h) > max_height_diff: problematic_points.append(((y,x),(ny,nx),abs(next_h-current_h)))
        return None, problematic_points
    path = []; curr = exit_coords
    while curr != entrance:
        path.append(curr)
        if feature_map[curr[0], curr[1]] == FEATURE_NONE: feature_map[curr[0], curr[1]] = FEATURE_PATH
        curr = parent[curr]
    path.append(entrance); path.reverse()
    feature_map[entrance[0], entrance[1]] = FEATURE_ENTRANCE; feature_map[exit_coords[0], exit_coords[1]] = FEATURE_EXIT
    # print(f"BFS 경로 찾음 (길이: {len(path)})") # 로그 출력 줄임
    return path, None

def adjust_heights_for_path(dungeon, height_map, problematic_points, max_height_diff=4):
    # ... (map7.py와 동일) ...
    # print(f"높이 조정 ({len(problematic_points)}개 지점)...") # 로그 출력 줄임
    adjusted_count = 0
    for (y1, x1), (y2, x2), height_diff in problematic_points:
        h1 = height_map[y1,x1] if height_map[y1,x1]>0 else 1; h2 = height_map[y2,x2] if height_map[y2,x2]>0 else 1
        actual_diff = abs(h1-h2)
        if actual_diff > max_height_diff:
            adjustment = (actual_diff-max_height_diff+1)//2
            new_h1, new_h2 = (h1+adjustment,h2-adjustment) if h1<h2 else (h1-adjustment,h2+adjustment)
            height_map[y1,x1] = max(1,new_h1); height_map[y2,x2] = max(1,new_h2); adjusted_count+=1
    # if adjusted_count > 0: print(f"{adjusted_count}개 조정 완료.") # 로그 출력 줄임
    return height_map

def ensure_path_exists(dungeon, height_map, feature_map, entrance, exit_coords, max_attempts=10, max_height_diff=4):
    # ... (map7.py와 거의 동일) ...
    if entrance is None or exit_coords is None: print("입/출구 설정 불가."); return height_map, feature_map, None
    for attempt in range(max_attempts):
        # print(f"경로 확인 #{attempt+1}/{max_attempts}...") # 로그 출력 줄임
        path, problematic_points = find_path_bfs(dungeon, height_map, feature_map, entrance, exit_coords, max_height_diff)
        if path: 
            # print("경로 발견!") # 로그 출력 줄임
            return height_map, feature_map, path
        if problematic_points: 
            # print(f"경로 없음. {len(problematic_points)}개 높이 조정...") # 로그 출력 줄임
            height_map = adjust_heights_for_path(dungeon, height_map, problematic_points, max_height_diff)
        else: 
            print("경로/조정 지점 없음. 강제 조정...")
            if entrance: height_map[entrance[0], entrance[1]] = 1
            if exit_coords: height_map[exit_coords[0], exit_coords[1]] = 1
            for r_off, c_off in itertools.product([-1,0,1],[-1,0,1]):
                 if r_off==0 and c_off==0: continue
                 if entrance:
                     nrE,ncE = entrance[0]+r_off,entrance[1]+c_off
                     if 0<=nrE<dungeon.shape[0] and 0<=ncE<dungeon.shape[1] and dungeon[nrE,ncE]==1:
                         height_map[nrE,ncE]=1
                 if exit_coords:
                     nrX,ncX = exit_coords[0]+r_off,exit_coords[1]+c_off
                     if 0<=nrX<dungeon.shape[0] and 0<=ncX<dungeon.shape[1] and dungeon[nrX,ncX]==1:
                         height_map[nrX,ncX]=1
    path, _ = find_path_bfs(dungeon, height_map, feature_map, entrance, exit_coords, max_height_diff)
    if path: print("최종 조정 후 경로 발견!"); return height_map, feature_map, path
    else: print(f"경고: {max_attempts}번 시도 후 경로 보장 실패."); return height_map, feature_map, None

def convert_dungeon_to_text_map(dungeon, height_map, feature_map, rooms):
    """던전을 텍스트 기반 맵으로 변환"""
    height, width = dungeon.shape
    text_map = []
    
    # 헤더 정보
    text_map.append("=== 던전 맵 (텍스트 표현) ===")
    text_map.append(f"크기: {width} x {height}")
    text_map.append(f"방 개수: {len(rooms)}")
    text_map.append("")
    
    # 범례
    text_map.append("범례:")
    text_map.append("  # : 벽")
    text_map.append("  . : 일반 통로/방")
    text_map.append("  E : 입구")
    text_map.append("  X : 출구")
    text_map.append("  T : 함정")
    text_map.append("  ? : 비밀통로 힌트")
    text_map.append("  O : 장애물")
    text_map.append("  B : 다리")
    text_map.append("  $ : 보물")
    text_map.append("  + : 주경로")
    text_map.append("  m : 약한 몬스터")
    text_map.append("  M : 일반 몬스터")
    text_map.append("  S : 강한 몬스터")
    text_map.append("  B : 보스 몬스터")
    text_map.append("")
    
    # 맵 생성
    for y in range(height):
        row = ""
        for x in range(width):
            if dungeon[y, x] == 0:
                row += "#"
            else:
                feature = feature_map[y, x]
                if feature == FEATURE_ENTRANCE:
                    row += "E"
                elif feature == FEATURE_EXIT:
                    row += "X"
                elif feature == FEATURE_TRAP:
                    row += "T"
                elif feature == FEATURE_SECRET_HINT:
                    row += "?"
                elif feature == FEATURE_OBSTACLE:
                    row += "O"
                elif feature == FEATURE_BRIDGE:
                    row += "B"
                elif feature == FEATURE_TREASURE:
                    row += "$"
                elif feature == FEATURE_PATH:
                    row += "+"
                elif feature == FEATURE_MONSTER_WEAK:
                    row += MONSTER_TYPES[FEATURE_MONSTER_WEAK]["symbol"]
                elif feature == FEATURE_MONSTER_NORMAL:
                    row += MONSTER_TYPES[FEATURE_MONSTER_NORMAL]["symbol"]
                elif feature == FEATURE_MONSTER_STRONG:
                    row += MONSTER_TYPES[FEATURE_MONSTER_STRONG]["symbol"]
                elif feature == FEATURE_MONSTER_BOSS:
                    row += MONSTER_TYPES[FEATURE_MONSTER_BOSS]["symbol"]
                else:
                    row += "."
        text_map.append(row)
    
    return "\n".join(text_map)

def convert_dungeon_to_json(dungeon, height_map, feature_map, rooms, path, entrance, exit_coords, monsters=None):
    """던전 데이터를 JSON 형태로 변환"""
    import json
    
    height, width = dungeon.shape
    
    # 기본 정보
    dungeon_data = {
        "metadata": {
            "width": int(width),
            "height": int(height),
            "room_count": len(rooms),
            "path_length": len(path) if path else 0
        },
        "entrance": {
            "coordinates": [int(entrance[1]), int(entrance[0])] if entrance else None,
            "description": "던전 입구"
        },
        "exit": {
            "coordinates": [int(exit_coords[1]), int(exit_coords[0])] if exit_coords else None,
            "description": "던전 출구"
        },
        "rooms": [],
        "features": [],
        "terrain": [],
        "path": [],
        "monsters": []
    }
    
    # 방 정보
    for i, (x, y, w, h) in enumerate(rooms):
        room_data = {
            "id": i,
            "coordinates": [int(x), int(y)],
            "size": [int(w), int(h)],
            "center": [int(x + w//2), int(y + h//2)],
            "area": int(w * h),
            "description": f"방 #{i+1} ({w}x{h})"
        }
        dungeon_data["rooms"].append(room_data)
    
    # 특성별 위치 수집
    feature_locations = {}
    for y in range(height):
        for x in range(width):
            if dungeon[y, x] == 1:  # 통행 가능한 지역만
                feature = feature_map[y, x]
                height_val = int(height_map[y, x])
                
                # 지형 정보
                terrain_info = {
                    "coordinates": [int(x), int(y)],
                    "height": height_val,
                    "feature": FEATURE_NAMES[feature],
                    "passable": True
                }
                dungeon_data["terrain"].append(terrain_info)
                
                # 특별한 특성이 있는 경우
                if feature != FEATURE_NONE:
                    if feature not in feature_locations:
                        feature_locations[feature] = []
                    feature_locations[feature].append([int(x), int(y)])
    
    # 특성 정보 정리
    for feature_type, locations in feature_locations.items():
        feature_info = {
            "type": FEATURE_NAMES[feature_type],
            "count": len(locations),
            "locations": locations,
            "description": get_feature_description(feature_type)
        }
        dungeon_data["features"].append(feature_info)
    
    # 경로 정보
    if path:
        for y, x in path:
            dungeon_data["path"].append([int(x), int(y)])
    
    # 몬스터 정보
    if monsters:
        for monster in monsters:
            dungeon_data["monsters"].append(monster)
    
    return json.dumps(dungeon_data, indent=2, ensure_ascii=False)

def get_feature_description(feature_type):
    """특성별 상세 설명"""
    descriptions = {
        FEATURE_TRAP: "위험한 함정이 설치된 지역. 주의해서 통과해야 함",
        FEATURE_SECRET_HINT: "숨겨진 통로나 비밀의 단서가 있을 만한 지역",
        FEATURE_OBSTACLE: "복도에 장애물이 있어 이동이 어려운 지역",
        FEATURE_BRIDGE: "높은 지대를 연결하는 다리 구조물",
        FEATURE_ENTRANCE: "던전의 입구. 모험이 시작되는 곳",
        FEATURE_EXIT: "던전의 출구. 목표 지점",
        FEATURE_PATH: "입구에서 출구로 이어지는 주요 경로",
        FEATURE_TREASURE: "귀중한 보물이 숨겨져 있을 만한 지역"
    }
    return descriptions.get(feature_type, "일반적인 통로나 방")

def create_llm_readable_description(dungeon, height_map, feature_map, rooms, path, entrance, exit_coords, monsters=None):
    """LLM이 이해하기 쉬운 던전 설명 생성"""
    height, width = dungeon.shape
    
    description = []
    description.append("=== 던전 맵 상세 설명 ===\n")
    
    # 기본 정보
    description.append(f"이 던전은 {width}x{height} 크기의 지하 미로입니다.")
    description.append(f"총 {len(rooms)}개의 방이 복도로 연결되어 있습니다.\n")
    
    # 입구와 출구
    if entrance and exit_coords:
        entrance_x, entrance_y = entrance[1], entrance[0]
        exit_x, exit_y = exit_coords[1], exit_coords[0]
        distance = abs(entrance_x - exit_x) + abs(entrance_y - exit_y)
        description.append(f"입구는 ({entrance_x}, {entrance_y}) 위치에 있고,")
        description.append(f"출구는 ({exit_x}, {exit_y}) 위치에 있습니다.")
        description.append(f"두 지점 사이의 맨해튼 거리는 {distance}입니다.\n")
    
    # 방 정보
    description.append("방 정보:")
    for i, (x, y, w, h) in enumerate(rooms):
        center_x, center_y = x + w//2, y + h//2
        area = w * h
        description.append(f"  방 {i+1}: 위치({x}, {y}), 크기({w}x{h}), 면적({area}), 중심({center_x}, {center_y})")
    description.append("")
    
    # 특성별 통계
    feature_counts = {}
    height_stats = {"min": float('inf'), "max": 0, "total": 0, "count": 0}
    
    for y in range(height):
        for x in range(width):
            if dungeon[y, x] == 1:
                feature = feature_map[y, x]
                feature_counts[feature] = feature_counts.get(feature, 0) + 1
                h = height_map[y, x]
                height_stats["min"] = min(height_stats["min"], h)
                height_stats["max"] = max(height_stats["max"], h)
                height_stats["total"] += h
                height_stats["count"] += 1
    
    description.append("던전 특성 분포:")
    for feature_type, count in feature_counts.items():
        if feature_type != FEATURE_NONE:
            percentage = (count / height_stats["count"]) * 100
            description.append(f"  {FEATURE_NAMES[feature_type]}: {count}개 ({percentage:.1f}%)")
    description.append("")
    
    # 높이 정보
    avg_height = height_stats["total"] / height_stats["count"]
    description.append(f"지형 높이 정보:")
    description.append(f"  최저 높이: {height_stats['min']}")
    description.append(f"  최고 높이: {height_stats['max']}")
    description.append(f"  평균 높이: {avg_height:.1f}")
    description.append("")
    
    # 경로 정보
    if path:
        description.append(f"입구에서 출구까지의 최단 경로는 {len(path)}단계입니다.")
        description.append("주요 경로상의 특별한 지점들:")
        path_features = {}
        for y, x in path:
            feature = feature_map[y, x]
            if feature not in [FEATURE_NONE, FEATURE_PATH, FEATURE_ENTRANCE, FEATURE_EXIT]:
                path_features[feature] = path_features.get(feature, 0) + 1
        
        for feature_type, count in path_features.items():
            description.append(f"  경로상 {FEATURE_NAMES[feature_type]}: {count}개")
        description.append("")
    
    # 몬스터 정보
    if monsters:
        description.append("몬스터 분포:")
        monster_by_type = {}
        total_level = 0
        max_danger = 0
        
        for monster in monsters:
            m_type = monster['type']
            if m_type not in monster_by_type:
                monster_by_type[m_type] = []
            monster_by_type[m_type].append(monster)
            total_level += monster['level']
            max_danger = max(max_danger, monster['hp'] + monster['attack'])
        
        for m_type, monster_list in monster_by_type.items():
            avg_level = sum(m['level'] for m in monster_list) / len(monster_list)
            description.append(f"  {m_type}: {len(monster_list)}마리 (평균 레벨 {avg_level:.1f})")
        
        avg_total_level = total_level / len(monsters) if monsters else 0
        description.append(f"  총 몬스터: {len(monsters)}마리")
        description.append(f"  평균 레벨: {avg_total_level:.1f}")
        description.append(f"  최고 위험도: {max_danger}")
        description.append("")
        
        # 위험한 몬스터들 나열
        dangerous_monsters = [m for m in monsters if m['level'] >= 8 or (m['hp'] + m['attack']) >= 60]
        if dangerous_monsters:
            description.append("⚠️ 특히 위험한 몬스터들:")
            for monster in dangerous_monsters[:5]:  # 최대 5마리만 표시
                pos = monster['position']
                description.append(f"  {monster['name']} (Lv.{monster['level']}) - 위치({pos[0]}, {pos[1]})")
    
    # 전략적 조언
    description.append("던전 탐험 조언:")
    if FEATURE_TRAP in feature_counts:
        description.append(f"  - {feature_counts[FEATURE_TRAP]}개의 함정이 있으니 주의하세요.")
    if FEATURE_TREASURE in feature_counts:
        description.append(f"  - {feature_counts[FEATURE_TREASURE]}개의 보물 지점이 있습니다.")
    if FEATURE_SECRET_HINT in feature_counts:
        description.append(f"  - {feature_counts[FEATURE_SECRET_HINT]}개의 비밀 힌트를 찾아보세요.")
    if monsters:
        weak_count = len([m for m in monsters if m['level'] <= 3])
        strong_count = len([m for m in monsters if m['level'] >= 7])
        description.append(f"  - 약한 몬스터 {weak_count}마리, 강한 몬스터 {strong_count}마리")
        if strong_count > 0:
            description.append("  - 강한 몬스터들과의 전투를 피하거나 충분히 준비하세요.")
    
    return "\n".join(description)

# ================== 메인 실행 부분 ==================

# 던전 생성 파라미터
width, height = 70, 60
room_count = 7
room_min, room_max = 8, 16
min_room_distance = 5
max_height = 18
max_height_diff = 4
trap_prob_base = 0.015
trap_prob_corridor_center = 0.005
treasure_prob = 0.02

# 던전 생성 시도
max_dungeon_attempts = 5
final_dungeon, final_rooms, final_path = None, None, None
final_height_map, final_feature_map = None, None
final_entrance, final_exit = None, None

for dungeon_attempt in range(max_dungeon_attempts):
    print(f"\n===== 던전 생성 시도 #{dungeon_attempt + 1} =====")
    dungeon, rooms, corridors = generate_dungeon(width, height, room_count, room_min, room_max, min_room_distance, extra_connection_prob=0.35)
    if len(rooms) < 2: print("방 부족, 재시도."); continue
    height_map, feature_map = generate_height_map(dungeon, rooms, corridors, max_height=max_height, 
                                                trap_prob_base=trap_prob_base, 
                                                trap_prob_corridor_center=trap_prob_corridor_center, 
                                                treasure_prob=treasure_prob)
    # ===== 입/출구 선택 로직 변경 =====
    entrance, exit_coords = select_entrance_exit(dungeon, rooms, height_map, feature_map)
    if entrance is None or exit_coords is None: print("입/출구 생성 실패, 재시도."); continue
    # print(f"입구: {entrance}, 출구: {exit_coords}") # 로그는 select 함수 내에서 출력
    
    adjusted_height_map, adjusted_feature_map, path = ensure_path_exists(
        dungeon, height_map, feature_map, entrance, exit_coords, max_height_diff=max_height_diff)
    if path:
        # ===== 몬스터 생성 =====
        monsters = generate_monsters(dungeon, rooms, adjusted_feature_map, entrance, exit_coords)
        print(f"몬스터 {len(monsters)}마리 생성 완료!")
        
        print("성공적인 던전 생성 완료!")
        final_dungeon, final_rooms = dungeon, rooms
        final_height_map, final_feature_map = adjusted_height_map, adjusted_feature_map
        final_entrance, final_exit, final_path = entrance, exit_coords, path
        final_monsters = monsters
        break
    else: print("경로 보장 실패, 재시도.")

if final_path is None: print(f"오류: {max_dungeon_attempts}번 시도에도 유효 경로 던전 생성 실패."); exit()

# ===== LLM용 데이터 생성 및 출력 =====
print("\n===== LLM용 데이터 생성 중... =====")

# 1. 텍스트 맵 생성
text_map = convert_dungeon_to_text_map(final_dungeon, final_height_map, final_feature_map, final_rooms)
print("텍스트 맵 생성 완료")

# 2. JSON 데이터 생성  
json_data = convert_dungeon_to_json(final_dungeon, final_height_map, final_feature_map, 
                                  final_rooms, final_path, final_entrance, final_exit, final_monsters)
print("JSON 데이터 생성 완료")

# 3. LLM용 설명 생성
llm_description = create_llm_readable_description(final_dungeon, final_height_map, final_feature_map,
                                                final_rooms, final_path, final_entrance, final_exit, final_monsters)
print("LLM용 설명 생성 완료")

# 데이터 파일 저장
with open('dungeon_text_map.txt', 'w', encoding='utf-8') as f:
    f.write(text_map)

with open('dungeon_data.json', 'w', encoding='utf-8') as f:
    f.write(json_data)

with open('dungeon_description.txt', 'w', encoding='utf-8') as f:
    f.write(llm_description)

print("\n파일 저장 완료:")
print("- dungeon_text_map.txt: 텍스트 기반 맵")
print("- dungeon_data.json: 구조화된 던전 데이터")  
print("- dungeon_description.txt: LLM용 상세 설명")

# 콘솔에 요약 출력
print("\n" + "="*50)
print("던전 요약 정보:")
print("="*50)
print(llm_description[:500] + "..." if len(llm_description) > 500 else llm_description)
print("="*50)

# ===== 시각화 부분 =====
tile_width, tile_height = 1.5, 0.75
height_scale = 0.4

fig, ax = plt.subplots(figsize=(24, 20), dpi=150)
ax.set_aspect('equal'); ax.axis('off')

# 바닥면
floor_poly = Polygon([
    (-width*tile_width/2, height*tile_height/2), (0,0), (width*tile_width/2, height*tile_height/2), (0, height*tile_height)],
    closed=True, alpha=0.15, facecolor='#404040', edgecolor='gray')
ax.add_patch(floor_poly)

# 컬러맵
colors = ['#2c3e50', '#3498db', '#1abc9c', '#f1c40f', '#e67e22', '#e74c3c']
cmap = LinearSegmentedColormap.from_list('custom_terrain', colors, N=256)

# 타일 정보 수집 및 정렬
tiles_to_draw = []
for y in range(height): 
    for x in range(width):
        if final_dungeon[y, x] == 1:
            h = final_height_map[y, x]; feature = final_feature_map[y, x]
            iso_x = (x - y) * tile_width / 2; iso_y = (x + y) * tile_height / 2
            tiles_to_draw.append({'x':x, 'y':y, 'h':h, 'feature':feature, 'iso_x':iso_x, 'iso_y':iso_y})

tiles_to_draw.sort(key=lambda t: (t['y'] + t['x'], t['h'])) # 렌더링 순서 (y+x, h)

# 타일 그리기 및 텍스트 추가
max_h_val = max(1, final_height_map.max())
feature_texts = []

for tile in tiles_to_draw:
    # ... (map7.py 시각화 로직과 동일) ...
    x, y, h, feature = tile['x'], tile['y'], tile['h'], tile['feature']
    iso_x, iso_y = tile['iso_x'], tile['iso_y']
    normalized_height = h / max_h_val; base_color = cmap(normalized_height)
    top_y_offset = iso_y - h * height_scale
    top_coord = (iso_x, top_y_offset); right_coord = (iso_x + tile_width/2, top_y_offset + tile_height/2)
    bottom_coord = (iso_x, top_y_offset + tile_height); left_coord = (iso_x - tile_width/2, top_y_offset + tile_height/2)
    left_side_color = tuple(c*0.5 for c in base_color[:3]) + (base_color[3],)
    right_side_color = tuple(c*0.7 for c in base_color[:3]) + (base_color[3],)
    tile_face_color = base_color; tile_edge_color = 'black'; tile_linewidth = 0.5
    text_label = None; text_color = 'white'; text_fontsize = 7
    if feature == FEATURE_BRIDGE:
         left_side_color = '#A0522D'; right_side_color = '#8B4513'
         tile_face_color = '#D2B48C'; tile_edge_color = '#8B4513'; tile_linewidth = 1.2
         text_label = 'B'; text_color = 'black'
    elif feature == FEATURE_ENTRANCE:
        tile_face_color = 'lime'; tile_linewidth = 1.5; text_label = 'E'; text_color = 'black'
    elif feature == FEATURE_EXIT:
        tile_face_color = 'red'; tile_linewidth = 1.5; text_label = 'X'; text_color = 'black'
    elif feature == FEATURE_PATH: tile_face_color = 'yellow'; tile_linewidth = 0.8
    elif feature == FEATURE_TRAP:
        tile_edge_color = 'red'; tile_linewidth = 1.0; text_label = 'T'; text_color = 'red'
    elif feature == FEATURE_SECRET_HINT:
        tile_edge_color = 'blue'; tile_linewidth = 1.0; text_label = '?'; text_color = 'blue'
    elif feature == FEATURE_OBSTACLE:
        tile_edge_color = 'gray'; tile_linewidth = 1.0; text_label = 'O'; text_color = 'dimgray'
    elif feature == FEATURE_TREASURE:
        tile_face_color = 'gold'; tile_edge_color = 'darkorange'; tile_linewidth = 1.0
        text_label = '$'; text_color = 'black'
    elif feature == FEATURE_MONSTER_WEAK:
        tile_face_color = 'lightcoral'; tile_edge_color = 'darkred'; tile_linewidth = 1.0
        text_label = 'm'; text_color = 'darkred'
    elif feature == FEATURE_MONSTER_NORMAL:
        tile_face_color = 'orange'; tile_edge_color = 'darkorange'; tile_linewidth = 1.0
        text_label = 'M'; text_color = 'darkred'
    elif feature == FEATURE_MONSTER_STRONG:
        tile_face_color = 'red'; tile_edge_color = 'darkred'; tile_linewidth = 1.0
        text_label = 'S'; text_color = 'white'
    elif feature == FEATURE_MONSTER_BOSS:
        tile_face_color = 'darkred'; tile_edge_color = 'black'; tile_linewidth = 2.0
        text_label = 'B'; text_color = 'yellow'
    if h > 0:
        left_side_coords = [left_coord, (left_coord[0], iso_y + tile_height/2), (iso_x, iso_y + tile_height), bottom_coord]
        left_poly = Polygon(left_side_coords, closed=True, facecolor=left_side_color, edgecolor='black', linewidth=0.2)
        ax.add_patch(left_poly)
        right_side_coords = [bottom_coord, (iso_x, iso_y + tile_height), (right_coord[0], iso_y + tile_height/2), right_coord]
        right_poly = Polygon(right_side_coords, closed=True, facecolor=right_side_color, edgecolor='black', linewidth=0.2)
        ax.add_patch(right_poly)
    top_poly_coords = [top_coord, right_coord, bottom_coord, left_coord]
    top_poly = Polygon(top_poly_coords, closed=True, facecolor=tile_face_color, edgecolor=tile_edge_color, linewidth=tile_linewidth)
    ax.add_patch(top_poly)
    if feature == FEATURE_EXIT:
        border_poly = Polygon(top_poly_coords, closed=True, facecolor='none', edgecolor='yellow', linewidth=2.5)
        ax.add_patch(border_poly)
    if text_label:
         text_x = iso_x; text_y = top_y_offset - tile_height * 0.1
         can_draw = True
         for tx, ty, _ in feature_texts:
              if abs(text_x - tx) < tile_width * 0.5 and abs(text_y - ty) < tile_height * 0.5:
                   can_draw = False; break
         if can_draw:
              ax.text(text_x, text_y, text_label, ha='center', va='center', 
                      fontsize=text_fontsize, color=text_color, fontweight='bold',
                      bbox=dict(boxstyle='circle,pad=0.1', fc='white', alpha=0.7, ec='none'))
              feature_texts.append((text_x, text_y, text_label))

# 축 범위 및 제목
ax.autoscale_view()
ax.set_title('개선된 쿼터뷰 던전 맵 v8 (입/출구 거리 최대화)', fontsize=18, pad=25)

plt.tight_layout()
plt.savefig('dungeon_map_v8.png', dpi=150, bbox_inches='tight')
plt.show() 

def demo_llm_analysis():
    """LLM이 던전 데이터를 분석하는 예시 함수"""
    print("\n" + "="*60)
    print("LLM 던전 분석 예시")
    print("="*60)
    
    # 저장된 파일들 읽기
    try:
        with open('dungeon_text_map.txt', 'r', encoding='utf-8') as f:
            text_map = f.read()
        
        with open('dungeon_data.json', 'r', encoding='utf-8') as f:
            import json
            dungeon_data = json.loads(f.read())
        
        with open('dungeon_description.txt', 'r', encoding='utf-8') as f:
            description = f.read()
        
        print("📊 데이터 로드 완료!")
        print(f"던전 크기: {dungeon_data['metadata']['width']}x{dungeon_data['metadata']['height']}")
        print(f"방 개수: {dungeon_data['metadata']['room_count']}")
        print(f"경로 길이: {dungeon_data['metadata']['path_length']}")
        
        # 특성별 위험도 분석
        print("\n🎯 위험도 분석:")
        danger_score = 0
        for feature in dungeon_data['features']:
            if feature['type'] == '함정':
                danger_score += feature['count'] * 3
                print(f"  함정 {feature['count']}개 발견 (위험도 +{feature['count']*3})")
            elif feature['type'] == '장애물':
                danger_score += feature['count'] * 1
                print(f"  장애물 {feature['count']}개 (난이도 +{feature['count']})")
        
        print(f"  총 위험도 점수: {danger_score}")
        
        # 보물 분석
        print("\n💎 보물 분석:")
        for feature in dungeon_data['features']:
            if feature['type'] == '보물':
                print(f"  보물 {feature['count']}개 발견!")
                for i, location in enumerate(feature['locations']):
                    print(f"    보물 {i+1}: 위치 ({location[0]}, {location[1]})")
        
        # 몬스터 분석
        if 'monsters' in dungeon_data and dungeon_data['monsters']:
            print("\n👹 몬스터 분석:")
            monsters = dungeon_data['monsters']
            monster_types = {}
            total_threat = 0
            
            for monster in monsters:
                m_type = monster['type']
                monster_types[m_type] = monster_types.get(m_type, 0) + 1
                total_threat += monster['level'] * 2 + monster['hp'] + monster['attack']
            
            print(f"  총 몬스터 수: {len(monsters)}마리")
            for m_type, count in monster_types.items():
                print(f"  {m_type}: {count}마리")
            
            avg_threat = total_threat / len(monsters)
            print(f"  평균 위험도: {avg_threat:.1f}")
            
            # 가장 위험한 몬스터
            most_dangerous = max(monsters, key=lambda m: m['level'] * 2 + m['hp'] + m['attack'])
            pos = most_dangerous['position']
            print(f"  가장 위험: {most_dangerous['name']} (Lv.{most_dangerous['level']}) - ({pos[0]}, {pos[1]})")
        
        # 전략적 조언
        print("\n🗺️ 탐험 전략:")
        entrance = dungeon_data['entrance']['coordinates']
        exit_coords = dungeon_data['exit']['coordinates']
        print(f"  시작점: ({entrance[0]}, {entrance[1]})")
        print(f"  목표점: ({exit_coords[0]}, {exit_coords[1]})")
        
        if dungeon_data['metadata']['path_length'] > 30:
            print("  ⚠️ 긴 경로 - 충분한 준비물 필요")
        else:
            print("  ✅ 적당한 길이의 경로")
            
        print("\n이러한 데이터를 바탕으로 LLM은 더욱 상세하고 개인화된")
        print("던전 가이드를 제공할 수 있습니다!")
        
    except FileNotFoundError:
        print("❌ 던전 데이터 파일을 찾을 수 없습니다.")
        print("먼저 던전을 생성해주세요.")

# 데모 실행
demo_llm_analysis()

print("\n🎮 사용법:")
print("1. 생성된 파일들을 LLM에게 제공")
print("2. '이 던전을 분석하고 탐험 가이드를 작성해주세요' 라고 요청")
print("3. LLM이 지도를 읽고 상세한 설명 제공")
print("\n생성된 파일:")
print("- dungeon_text_map.txt    # 텍스트 맵")
print("- dungeon_data.json       # 구조화된 데이터") 
print("- dungeon_description.txt # 상세 설명")
print("- dungeon_map_v8.png      # 시각적 맵") 