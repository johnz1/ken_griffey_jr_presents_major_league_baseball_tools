These are the tools that I developed in September 2025 for Ken Griffey Jr. Presents Major League Baseball for the SNES.  The KGB Editor (by JG) has been a great tool for a very long time, but I wanted more control and more things to edit (like batting stances, pitcher glasses, "10" ratings, and home run derby players).


# ROM Modifier Script
This script applies the data in the SQLite DB to the SNES ROM file.  It was designed to manage the game's entire roster.  It should work with header and headerless ROM files, but I only tested it against a headerless ROM.
Please note that I am not very experienced with Python.  This may be very obvious when you look at the code.  I used ChatGPT 4.1 to get started, but most of the work was done by me.

Before writing to the ROM, the script performs several sanity checks:
- Every team has exactly 25 players in 'team_lineups_$YEAR'
- There are exactly 700 rows in 'team_lineups_$YEAR' (28 teams, 25 players per team)
- Every team has exactly one of every position in their starting lineup


# SQLite Projects Database
All player and team data is stored in the SQLite DB.  This was designed to support multiple seasons in a single DB, so some tables and columns need to have the year in their name.  The 2007 season has been included as examples of this.  For my 2007 project, I used stats from baseballguru.com (in the 'stats_2007' table), which uses the same player ID's as baseball-reference.com.

## 'players' table
These columns in the 'players' table are not used by the ROM modifier script:
- 'age_$YEAR'
- 'team_$YEAR'
- 'position'
- 'confirmed_bat_appearance' (I use this for tracking which players have been verified in-game)
- 'height_in'
- 'weight_lb'

Here are value mappings for columns in the 'players' table:
- throwing_style
  - 0 = Regular overhand
  - 1 = Sidearm/submarine
- appearance_bat_skin
  - 0 = White
  - 1 = Tan
  - 2 = Very tan
  - 3 = Light black
  - 4 = Black
  - 5 = Dark black
- appearance_bat_head
  - 0 = Average hair, no facial hair
  - 1 = Average hair, mustache
  - 2 = Average hair, beard
  - 3 = Average hair, goatee
  - 4 = Medium long hair, no facial hair
  - 5 = Average hair, mustache
  - 6 = Average hair, beard
  - 7 = Long hair, no facial hair
- appearance_bat_hair_color
  - 0 = Blonde/Brown
  - 1 = Red
  - 2 = Brown
  - 3 = Bald
  - 4 = Black
  - 5 = Blonde
- appearance_bat_body (I have not figured out exactly what the difference is between all of these)
  - 0 = Average ?
  - 1 = Skinny ?
  - 2 = Big, bat held close to body ?
  - 3 = Small ?
  - 4 = Big, bat held away from body ?
  - 5 = Average ?
  - 6 = Small ?
  - 7 = Average ?
- appearance_bat_legs_size
  - 0 = Average
  - 1 = Small
- appearance_bat_legs_stance
  - 0 = Slightly bent, medium distance apart
  - 1 = Straight, far apart
  - 2 = Slightly bent, pressed together
  - 3 = Significantly bent, medium distance apart
  - 4 = Front leg straight, back leg bent
- appearance_bat_arms_stance
  - 0 = Bat held close to body, straight up
  - 1 = Bat held far away from body
  - 2 = Bat held at medium distance away from body, at 45 degree angle
- appearance_pit_head
  - 0 = Average hair, no facial hair
  - 1 = Average hair, beard
  - 2 = Long hair, no facial hair
  - 3 = Average hair, mustache
  - 4 = Glasses, average hair, no facial hair
- appearance_pit_hair_color
  - 0 = Blonde
  - 1 = Red
  - 2 = Blonde/Brown
  - 3 = Brown
  - 4 = Black
- appearance_pit_skin
  - 0 = White
  - 1 = Tan
  - 2 = Very tan
  - 3 = Light black
  - 4 = Black
  - 5 = Dark black
- appearance_pit_body
  - 0 = Average
  - 1 = Fat
  - 2 = Tall
