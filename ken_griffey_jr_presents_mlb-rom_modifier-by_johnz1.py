import argparse
import sqlite3
import sys

# Configurable defaults
#DEFAULT_DB_PATH = ""

# Parse arguments
parser = argparse.ArgumentParser(description="Update Ken Griffey Jr. Presents Major League Baseball SNES ROM with stats from a SQLite DB.  Created by johnz1.")
parser.add_argument("romfile", help="Ken Griffey Jr. Presents Major League Baseball SNES ROM file to update (will be overwritten!)")
parser.add_argument("--db", help=f"Path to the SQLite database (default: {DEFAULT_DB_PATH})", default=DEFAULT_DB_PATH)
parser.add_argument("--year", required=True, type=int, help="Year of stats to use")
args = parser.parse_args()

# Set variables for tables
hr_derby_table = f"home_run_derby_lineups_{args.year}"
lineup_table = f"team_lineups_{args.year}"
ratings_table = f"ratings_{args.year}"
stats_table = f"stats_{args.year}"

# Connect to the DB
conn = sqlite3.connect(args.db)
cur = conn.cursor()

# Team and ROM structure info
cur.execute(f"SELECT DISTINCT team_stock, team_{args.year} FROM {lineup_table}")
teams = cur.fetchall()
TEAMS_STOCK_ORDER = [
    "BAL", "BOS", "CAL", "CHW", "CLE", "DET", "KC", "MIL", "MIN", "NYY", "OAK", "SEA", "TEX", "TOR",
    "ATL", "CHC", "CIN", "HOU", "LAD", "MON", "NYM", "PIT", "STL", "SD", "SF", "PHI", "COL", "FLA"
]
TEAM_OFFSETS = {}
PLAYER_LENGTH = 0x20
TEAM_LENGTH = 0x320
AL_TO_NL_GAP = 0xB40
FIRST_TEAM_MARKER = bytes([0x81, 0x81, 0x81, 0x81, 0x9F, 0x9F, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0xF0, 0xF0])
HR_DERBY_MARKER = bytes([0x02, 0x2E, 0x37, 0x27, 0x00, 0x0A, 0x23, 0x3B, 0x35, 0xFF])
HR_DERBY_BATTER_COUNT = 6

# Character mapping
CHAR_MAP = {
    ' ': 0x00,
    '0': 0x01, '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06, '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A,
    'A': 0x0B, 'B': 0x0C, 'C': 0x0D, 'D': 0x0E, 'E': 0x0F, 'F': 0x10, 'G': 0x11, 'H': 0x12, 'I': 0x13, 'J': 0x14,
    'K': 0x15, 'L': 0x16, 'M': 0x17, 'N': 0x18, 'O': 0x19, 'P': 0x1A, 'Q': 0x1B, 'R': 0x1C, 'S': 0x1D, 'T': 0x1E,
    'U': 0x1F, 'V': 0x20, 'W': 0x21, 'X': 0x22, 'Y': 0x23, 'Z': 0x24,
    'c': 0x36,
}

# Position mapping
POS_MAP = {
    "P":  0x00,
    "C":  0x02,
    "LF": 0x04,
    "CF": 0x06,
    "RF": 0x08,
    "3B": 0x0A,
    "SS": 0x0C,
    "2B": 0x0E,
    "1B": 0x10,
    "DH": 0x12,
    "IF": 0x14,
    "OF": 0x16,
}
POS_MAP_AL = set(POS_MAP.keys()) - {"P", "IF", "OF"}
POS_MAP_NL = set(POS_MAP.keys()) - {"P", "DH", "IF", "OF"}

# Batting handedness mapping
HAND_MAP = {
    "R": 0x00,
    "L": 0x11,
    "B": 0x20,
}

# Ensure there are exactly 700 rows in team_lineups_$YEAR
cur.execute(f"SELECT COUNT(*) FROM {lineup_table}")
count = cur.fetchone()[0]
if count != 700:
    print(f"ERROR: The {lineup_table} has {count} rows.  It should have exactly 700 rows (28 teams, each with 25 players).  Aborting.")
    conn.close()
    sys.exit(1)

# Ensure every team has exactly 25 players in team_lineups_$YEAR
for team_stock in TEAMS_STOCK_ORDER:
    cur.execute(f"SELECT COUNT(*) FROM {lineup_table} WHERE team_stock = ?", (team_stock,))
    count = cur.fetchone()[0]
    if count != 25:
        print(f"ERROR: Team {team_stock} has {count} players in {lineup_table} (should be 25). Aborting.")
        conn.close()
        sys.exit(1)

def find_first_team_offset(data):
    idx = data.find(FIRST_TEAM_MARKER)
    if idx == -1:
        raise Exception("ERROR: First team marker sequence not found!")
    return idx + len(FIRST_TEAM_MARKER)

def find_first_hr_derby_player_offset(data):
    idx = data.find(HR_DERBY_MARKER)
    if idx == -1:
        raise Exception("ERROR: Home Run Derby marker sequence not found!")
    return idx + len(HR_DERBY_MARKER)

def encode_player_name(first_name, last_name):
    # First initial
    initial = first_name[0].upper() if first_name else ' '
    initial_byte = CHAR_MAP.get(initial, 0x00)

    # Pad last name to at least 3 chars for safe indexing
    padded_last = last_name.ljust(3)

    last_name_bytes = []
    for i, ch in enumerate(padded_last[:8]):  # Only process first 8 characters
        if ch == ' ':
            code = CHAR_MAP[' ']
        elif i == 1 and ch.lower() == 'c' and padded_last[2].isupper():
            code = CHAR_MAP['c']
        else:
            code = CHAR_MAP.get(ch.upper(), None)
        if code is not None:
            last_name_bytes.append(code)
        # else: skip characters not in CHAR_MAP

    # Pad to 8 bytes if needed
    while len(last_name_bytes) < 8:
        last_name_bytes.append(CHAR_MAP[' '])

    return [initial_byte] + last_name_bytes[:8]

def write_all_player_values(player_bytes, cur, player_id, year, roster_position):
    # Player Position (0x09)
    cur.execute(f"SELECT position FROM {lineup_table} WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    pos = row[0] if row else None
    if pos is not None and pos in POS_MAP:
        player_bytes[0x09] = POS_MAP[pos]
    elif pos is not None:
        print(f"WARNING: Unknown position '{pos}' for {player_id}, skipping")

    # Jersey Number (0x0A)
    jersey_num_column = f"jersey_number_{args.year}"
    cur.execute(f"SELECT {jersey_num_column} FROM players WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    jersey_num = row[0] if row else None
    if jersey_num is None:
        print(f"WARNING: {jersey_num_column} is NULL for {player_id}, setting to #0")
        jersey_num = 0
    player_bytes[0x0A] = int(jersey_num) & 0xFF

    # Batting Handedness (0x0D)
    cur.execute("SELECT handedness_batting FROM players WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    bat_hand = row[0] if row else None
    if bat_hand is None:
        print(f"WARNING: 'handedness_batting' is NULL for {player_id}, setting to R")
        bat_hand = "R"
    if bat_hand in HAND_MAP:
        player_bytes[0x0D] = HAND_MAP[bat_hand]
    else:
        print(f"WARNING: Unknown batting handedness '{bat_hand}' for {player_id}, skipping")

    # Batting Skin Color, Batting Head (0x0E)
    cur.execute("SELECT appearance_bat_skin, appearance_bat_head FROM players WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    bat_skin, bat_head = row if row else (None, None)
    if bat_skin is None:
        print(f"WARNING: 'appearance_bat_skin' is NULL for {player_id}, skipping")
    else:
        player_bytes[0x0E] = (player_bytes[0x0E] & 0x0F) | ((bat_skin & 0x0F) << 4)
    if bat_head is None:
        print(f"WARNING: 'appearance_bat_head' is NULL for {player_id}, skipping")
    else:
        player_bytes[0x0E] = (player_bytes[0x0E] & 0xF0) | (bat_head & 0x0F)

    # Batting Hair Color, Batting Body (0x0F)
    cur.execute("SELECT appearance_bat_hair_color, appearance_bat_body FROM players WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    bat_hair, bat_body = row if row else (None, None)
    if bat_hair is None:
        print(f"WARNING: 'appearance_bat_hair_color' is NULL for {player_id}, skipping")
    else:
        player_bytes[0x0F] = (player_bytes[0x0F] & 0x0F) | ((bat_hair & 0x0F) << 4)
    if bat_body is None:
        print(f"WARNING: 'appearance_bat_body' is NULL for {player_id}, skipping")
    else:
        player_bytes[0x0F] = (player_bytes[0x0F] & 0xF0) | (bat_body & 0x0F)

    # Batting Legs Size, Batting Legs Stance (0x10)
    cur.execute("SELECT appearance_bat_legs_size, appearance_bat_legs_stance FROM players WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    bat_legs_size, bat_legs_stance = row if row else (None, None)
    if bat_legs_size is None:
        print(f"WARNING: 'appearance_bat_legs_size' is NULL for {player_id}, skipping")
    else:
        player_bytes[0x10] = (player_bytes[0x10] & 0x0F) | ((bat_legs_size & 0x0F) << 4)
    if bat_legs_stance is None:
        print(f"WARNING: 'appearance_bat_legs_stance' is NULL for {player_id}, skipping")
    else:
        player_bytes[0x10] = (player_bytes[0x10] & 0xF0) | (bat_legs_stance & 0x0F)

    # Unknown, Batting Arms Stance (0x11)
    cur.execute("SELECT appearance_bat_arms_stance FROM players WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    bat_arms = row[0] if row else None
    if bat_arms is None:
        print(f"WARNING: 'appearance_bat_arms_stance' is NULL for {player_id}, setting to 0")
        bat_arms = 0
    player_bytes[0x11] = (player_bytes[0x11] & 0xF0) | (bat_arms & 0x0F)

    # Unknown (0x19 high nibble)
    if 1 <= roster_position <= 15:
        unknown_0x19_high = 0x3  # batters
    elif 16 <= roster_position <= 20:
        unknown_0x19_high = 0x1  # starting pitchers
    elif 21 <= roster_position <= 25:
        unknown_0x19_high = 0x0  # relief pitchers
    else:
        print(f"ERROR: Roster position isn't between 1 and 25 {player_id}")
        unknown_0x19_high = (player_bytes[0x19] >> 4)  # leave unchanged if out of range
    player_bytes[0x19] = (player_bytes[0x19] & 0x0F) | (unknown_0x19_high << 4)

    # Unknown ("00" for all players) (0x1B)
    player_bytes[0x1B] = 0x00

    # Unknown (0x1D high nibble)
    if 1 <= roster_position <= 15:
        unknown_0x1d_high = 0x1  # batters
    elif 16 <= roster_position <= 25:
        unknown_0x1d_high = 0x2  # pitchers
    else:
        print(f"ERROR: Roster position isn't between 1 and 25 {player_id}")
        unknown_0x1d_high = (player_bytes[0x1D] >> 4)  # leave unchanged if out of range
    player_bytes[0x1D] = (player_bytes[0x1D] & 0x0F) | (unknown_0x1d_high << 4)

def write_batter_values(player_bytes, player_id, year, avg, hr, rbi):
    # BAT Rating, POW Rating (0x0B)
    cur.execute(f"SELECT rating_bat_bat, rating_bat_pow FROM {ratings_table} WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    rating_bat, rating_pow = row if row else (None, None)
    if rating_bat is None:
        print(f"WARNING: 'rating_bat_bat' is NULL for {player_id}, setting to 1")
        rating_bat = 1
    if rating_pow is None:
        print(f"WARNING: 'rating_bat_pow' is NULL for {player_id}, setting to 1")
        rating_pow = 1
    player_bytes[0x0B] = (rating_bat - 1 << 4) | (rating_pow - 1 & 0x0F)

    # SPD Rating, DEF Rating (0x0C)
    cur.execute(f"SELECT rating_bat_spd, rating_bat_def FROM {ratings_table} WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    rating_spd, rating_def = row if row else (None, None)
    if rating_spd is None:
        print(f"WARNING: 'rating_bat_spd' is NULL for {player_id}, setting to 1")
        rating_spd = 1
    if rating_def is None:
        print(f"WARNING: 'rating_bat_def' is NULL for {player_id}, setting to 1")
        rating_def = 1
    player_bytes[0x0C] = (rating_spd - 1 << 4) | (rating_def - 1 & 0x0F)

    # Pitching Handedness (always zero), Pitching Skin Color (always zero) (0x15)
    player_bytes[0x15] = 0x00

    # Pitching Head (always zero), Pitching Hair Color (always zero) (0x16)
    player_bytes[0x16] = 0x00

    # Pitching Body (always zero), Pitch Throwing Style (always zero) (0x17)
    player_bytes[0x17] = 0x00

    # AVG: Multiply by 1000, convert to hex (0x18, 0x19)
    if avg is None:
        print(f"WARNING: 'avg' is NULL for {player_id}, setting to .000")
        avg = 0.000
    avg_val = int(round(avg * 1000))
    avg_hex = f"{avg_val:03X}"  # always at least 3 hex digits
    # Split into hundreds, tens, ones in hex
    hundreds = int(avg_hex[-3], 16) if len(avg_hex) == 3 else 0
    tens_ones = int(avg_hex[-2:], 16)
    # 0x18: hex tens/ones
    player_bytes[0x18] = tens_ones
    # 0x19: preserve upper nibble, set lower nibble to hundreds
    player_bytes[0x19] = (player_bytes[0x19] & 0xF0) | (hundreds & 0x0F)

    # HR (0x1A)
    if hr is None:
        print(f"WARNING: 'hr' is NULL for {player_id}, setting to 0")
        hr = 0
    player_bytes[0x1A] = int(hr)

    # RBI (0x1C)
    if rbi is None:
        print(f"WARNING: 'rbi' is NULL for {player_id}, setting to 0")
        rbi = 0
    player_bytes[0x1C] = int(rbi)

    # Unknown ("10" for all batters) (0x1D)
    player_bytes[0x1D] = 0x10

def write_pitcher_values(player_bytes, player_id, year, wins, losses, sv, era):
    # SPD Rating, CON Rating (0x0B)
    cur.execute(f"SELECT rating_pit_spd, rating_pit_con FROM {ratings_table} WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    rating_spd, rating_con = row if row else (None, None)
    if rating_spd is None:
        print(f"WARNING: 'rating_pit_spd' is NULL for {player_id}, setting to 1")
        rating_spd = 1
    if rating_con is None:
        print(f"WARNING: 'rating_pit_con' is NULL for {player_id}, setting to 1")
        rating_con = 1
    player_bytes[0x0B] = (rating_spd - 1 << 4) | (rating_con - 1 & 0x0F)

    # Unknown (always zero), FAT rating (0x0C)
    cur.execute(f"SELECT rating_pit_fat FROM {ratings_table} WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    rating_fat = row[0] if row else None
    if rating_fat is None:
        print(f"WARNING: 'rating_pit_fat' is NULL for {player_id}, setting to 1")
        rating_fat = 1
    player_bytes[0x0C] = (rating_fat - 1) & 0x0F

    # Pitching Handedness, Pitching Skin Color (0x15)
    cur.execute("SELECT handedness_throwing, appearance_pit_skin FROM players WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    pit_hand, pit_skin = row if row else (None, None)
    # Only write pit_hand if it is valid
    if pit_hand is None:
        print(f"WARNING: 'handedness_throwing' is NULL for {player_id}, setting to R")
    if pit_hand == "R":
        pit_hand_val = 0
    elif pit_hand == "L":
        pit_hand_val = 1
    else:
        print(f"ERROR: Pitching handedness is invalid for {player_id}, skipping high nibble of 0x15")
        pit_hand_val = None
    if pit_hand_val is not None:
        player_bytes[0x15] = (player_bytes[0x15] & 0x0F) | ((pit_hand_val & 0x0F) << 4)
    # Only write pit_skin if not NULL
    if pit_skin is None:
        print(f"WARNING: 'appearance_pit_skin' is NULL for {player_id}, skipping")
    player_bytes[0x15] = (player_bytes[0x15] & 0xF0) | (pit_skin & 0x0F)

    # Pitching Head, Pitching Hair Color (0x16)
    cur.execute("SELECT appearance_pit_head, appearance_pit_hair_color FROM players WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    pit_head, pit_hair_color = row if row else (None, None)
    if pit_head is None:
        print(f"WARNING: 'appearance_pit_head' is NULL for {player_id}, skipping")
    else:
        player_bytes[0x16] = (player_bytes[0x16] & 0x0F) | ((pit_head & 0x0F) << 4)
    if pit_hair_color is None:
        print(f"WARNING: 'appearance_pit_hair_color' is NULL for {player_id}, skipping")
    else:
        player_bytes[0x16] = (player_bytes[0x16] & 0xF0) | (pit_hair_color & 0x0F)

    # Pitching Body, Pitch Throwing Style (0x17)
    cur.execute("SELECT appearance_pit_body, throwing_style FROM players WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    pit_body, throwing_style = row if row else (None, None)
    if pit_body is None:
        print(f"WARNING: 'appearance_pit_body' is NULL for {player_id}, skipping")
    else:
        player_bytes[0x17] = (player_bytes[0x17] & 0x0F) | ((pit_body & 0x0F) << 4)
    if throwing_style is None:
        print(f"WARNING: 'throwing_style' is NULL for {player_id}, setting to 0")
        throwing_style = 0
    player_bytes[0x17] = (player_bytes[0x17] & 0xF0) | (throwing_style & 0x0F)

    # W (0x18)
    if wins is None:
        print(f"WARNING: 'wins' is NULL for {player_id}, setting to 0")
        wins = 0
    player_bytes[0x18] = int(wins)

    # Unknown (lower nibble "0" for all pitchers) (0x19)
    player_bytes[0x19] = player_bytes[0x19] & 0xF0

    # L (0x1A)
    if losses is None:
        print(f"WARNING: 'losses' is NULL for {player_id}, setting to 0")
        losses = 0
    player_bytes[0x1A] = int(losses)

    # Unknown (upper nibble "2" for all pitchers) (0x1D)
    player_bytes[0x1D] = (player_bytes[0x1D] & 0x0F) | 0x20

    # SV (0x1E)
    if sv is None:
        print(f"WARNING: 'sv' is NULL for {player_id}, setting to 0")
        sv = 0
    player_bytes[0x1E] = int(sv)

    # ERA (0x1C, 0x1D)
    if era is None:
        print(f"WARNING: 'era' is NULL for {player_id}, setting to 0.00")
        era = 0.00
    era_val = int(round(era * 100))
    era_hex = f"{era_val:03X}"
    hundreds = int(era_hex[-3], 16) if len(era_hex) == 3 else 0
    tens_ones = int(era_hex[-2:], 16)
    # 0x1C: tens/ones
    player_bytes[0x1C] = tens_ones
    # 0x1D: preserve upper nibble, set lower nibble to hundreds
    player_bytes[0x1D] = (player_bytes[0x1D] & 0xF0) | (hundreds & 0x0F)

def verify_team_lineups(cur, year):
    # Get all teams and their league
    cur.execute(f"SELECT DISTINCT team_{year}, league FROM team_lineups_{year}")
    teams = cur.fetchall()
    errors = []

    for team_id, league in teams:
        # Get first n lineup positions for this team
        n = 9 if league == "AL" else 8
        pos_map = POS_MAP_AL if league == "AL" else POS_MAP_NL
        cur.execute(
            f"""SELECT position
                FROM team_lineups_{year}
                WHERE team_{year} = ? AND roster_position BETWEEN 1 AND ?
                ORDER BY roster_position""",
            (team_id, n)
        )
        positions = [row[0] for row in cur.fetchall()]
        # Check for missing or duplicate positions
        missing = set(pos_map) - set(positions)
        extra = [p for p in positions if positions.count(p) > 1]
        if missing or extra or len(positions) != n:
            errors.append({
                "team": team_id,
                "league": league,
                "missing": missing,
                "extra": set([p for p in positions if positions.count(p) > 1]),
                "positions": positions
            })

    if errors:
        for err in errors:
            print(f"Lineup error for team {err['team']} ({err['league']}):")
            if err["missing"]:
                print(f"  Missing: {', '.join(err['missing'])}")
            if err["extra"]:
                print(f"  Duplicate(s): {', '.join(err['extra'])}")
            print(f"  Positions found: {err['positions']}")
        raise Exception("Lineup verification failed! See errors above.")

def main():
    # Open and read ROM
    with open(args.romfile, "rb") as f:
        rom_data = bytearray(f.read())

    # Verify that every team has all of the required positions
    verify_team_lineups(cur, args.year)

    # Find first team offset
    first_team_offset = find_first_team_offset(rom_data)

    # Populate TEAM_OFFSETS
    TEAM_OFFSETS = {}
    for idx, team_stock in enumerate(TEAMS_STOCK_ORDER):
        if idx <= 13:  # AL
            offset = first_team_offset + idx * TEAM_LENGTH
        else:  # NL
            offset = first_team_offset + 14 * TEAM_LENGTH + AL_TO_NL_GAP + (idx - 14) * TEAM_LENGTH
        TEAM_OFFSETS[team_stock] = offset

    for team_stock in TEAMS_STOCK_ORDER:
        team_offset = TEAM_OFFSETS[team_stock]

        # Get player_ids for this team
        cur.execute(f"""
            SELECT player_id
            FROM {lineup_table}
            WHERE team_stock = ?
            ORDER BY roster_position ASC
            LIMIT 25
        """, (team_stock,))
        player_ids = [row[0] for row in cur.fetchall()]
        if len(player_ids) < 25:
            print(f"Warning: Only found {len(player_ids)} players for {team}")

        for idx, player_id in enumerate(player_ids):
            player_offset = team_offset + idx * PLAYER_LENGTH
            player_bytes = rom_data[player_offset:player_offset+PLAYER_LENGTH]

            # Set player names
            cur.execute("""
                SELECT first_name, last_name
                FROM players
                WHERE player_id = ?
            """, (player_id,))
            name_row = cur.fetchone()
            if name_row:
                first_name, last_name = name_row
                name_bytes = encode_player_name(first_name, last_name)
                player_bytes[0x00] = name_bytes[0]
                player_bytes[0x01:0x09] = name_bytes[1:9]
            else:
                print(f"Warning: No name found for player_id={player_id}")

            # Get roster position and set unknown bytes
            cur.execute(f"SELECT roster_position FROM {lineup_table} WHERE player_id = ?", (player_id,))
            roster_position = cur.fetchone()[0]

            # Set values common to all players
            write_all_player_values(player_bytes, cur, player_id, args.year, roster_position)

            if idx < 15:
                # Batters
                cur.execute(f"""
                    SELECT pl.handedness_batting, st.avg, st.hr, st.rbi
                    FROM players pl
                    JOIN {stats_table} st ON st.player_id = pl.player_id
                    WHERE pl.player_id = ?
                """, (player_id,))
                row = cur.fetchone()
                if not row:
                    print(f"Warning: No player data for player_id={player_id} ({team} batter #{idx+1})")
                    continue
                bat_hand, avg, hr, rbi = row
                write_batter_values(player_bytes, player_id, args.year, avg, hr, rbi)
            else:
                # Pitchers
                cur.execute(f"""
                    SELECT st.w, st.l, st.sv, st.era
                    FROM players pl
                    JOIN {stats_table} st ON st.player_id = pl.player_id
                    WHERE pl.player_id = ?
                """, (player_id,))
                row = cur.fetchone()
                if not row:
                    print(f"Warning: No pitcher data for player_id={player_id} ({team} pitcher #{idx-14})")
                    continue
                wins, losses, sv, era = row
                write_pitcher_values(player_bytes, player_id, args.year, wins, losses, sv, era)

            # Write back to ROM
            rom_data[player_offset:player_offset+PLAYER_LENGTH] = player_bytes

    # Find the first home run derby player offset
    first_hr_derby_player_offset = find_first_hr_derby_player_offset(rom_data)

    # Get the home run derby players from the database
    cur.execute(f"""
        SELECT league, roster_position, player_id
        FROM {hr_derby_table}
        ORDER BY
            CASE league WHEN 'NL' THEN 0 WHEN 'AL' THEN 1 ELSE 2 END,
            roster_position
    """)
    hr_derby_players = cur.fetchall()
    if len(hr_derby_players) != HR_DERBY_BATTER_COUNT:
        raise Exception(f"Expected {HR_DERBY_BATTER_COUNT} HR Derby batters, found {len(hr_derby_players)}")

    # Write the home run derby players
    for i, (league, roster_position, player_id) in enumerate(hr_derby_players):
        player_bytes = bytearray(PLAYER_LENGTH)
        write_all_player_values(player_bytes, cur, player_id, args.year, roster_position)

        cur.execute("""
            SELECT first_name, last_name
            FROM players
            WHERE player_id = ?
        """, (player_id,))
        name_row = cur.fetchone()
        if name_row:
            first_name, last_name = name_row
            name_bytes = encode_player_name(first_name, last_name)
            player_bytes[0x00] = name_bytes[0]
            player_bytes[0x01:0x09] = name_bytes[1:9]
        else:
            print(f"Warning: No name found for player_id={player_id}")

        cur.execute(f"""
            SELECT pl.handedness_batting, st.avg, st.hr, st.rbi
            FROM players pl
            JOIN {stats_table} st ON st.player_id = pl.player_id
            WHERE pl.player_id = ?
        """, (player_id,))
        row = cur.fetchone()
        if not row:
            print(f"Warning: No player data for player_id={player_id} ({team} batter #{idx+1})")
            continue
        bat_hand, avg, hr, rbi = row
        write_batter_values(player_bytes, player_id, args.year, avg, hr, rbi)

        # Write back to ROM
        offset = first_hr_derby_player_offset + i * PLAYER_LENGTH
        rom_data[offset:offset+PLAYER_LENGTH] = player_bytes

    # Write the home run derby full names


    # Overwrite input ROM file, and close the database connection
    with open(args.romfile, "wb") as f:
        f.write(rom_data)
    conn.close()
    print(f"ROM successfully updated for year {args.year}.")

if __name__ == "__main__":
    main()

