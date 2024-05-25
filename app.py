import pandas as pd
from flask import Flask, render_template, request
from espn_api.football import League
import os
import re
import pickle

app = Flask(__name__)

UPLOAD_FOLDER = '/Users/shraydewan/Downloads/draftdata'
CACHE_FOLDER = 'cache'
ALLOWED_EXTENSIONS = {'csv'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CACHE_FOLDER'] = CACHE_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

if not os.path.exists(CACHE_FOLDER):
    os.makedirs(CACHE_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def read_csv_files():
    dataframes = []
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        if filename.endswith(".csv"):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            df = pd.read_csv(file_path)
            year_match = re.search(r'\d{4}', filename)
            year = int(year_match.group()) if year_match else None
            if 'Year' in df.columns:
                df.rename(columns={'Year': 'Original Year'}, inplace=True)
            df['Year'] = year  # Add the year as a column
            dataframes.append(df)
    if dataframes:
        combined_df = pd.concat(dataframes, ignore_index=True)
        # Ensure the 'Year' column is consistently the first column
        cols = combined_df.columns.tolist()
        cols.insert(0, cols.pop(cols.index('Year')))
        combined_df = combined_df[cols]
        combined_df = combined_df[['Year', 'Pick #', 'Round Pick #', 'Owner', 'Previous Owner(s)', 'Pick', 'Team', 'Pos.']]  # Rearrange columns
    else:
        combined_df = pd.DataFrame()
    return combined_df

def replace_names(df):
    df.replace("Mani Suresh", "Rohan Shiknis", inplace=True)
    df.replace("Insung Kim", "Deven Chatterjea", inplace=True)
    df.replace("sainath raj", "Sainath Rajendrakumar", inplace=True)
    if 'Owner' in df.columns and 'Year' in df.columns:
        df.loc[(df['Year'] != 2019) & (df['Owner'] == "Rushil Knagaram"), 'Owner'] = "Liam Das"
    return df

def cache_data(data, filename):
    with open(os.path.join(app.config['CACHE_FOLDER'], filename), 'wb') as f:
        pickle.dump(data, f)

def load_cached_data(filename):
    with open(os.path.join(app.config['CACHE_FOLDER'], filename), 'rb') as f:
        return pickle.load(f)

def get_box_scores(league_id, swid, espn_s2, year, weeks):
    cache_file = f'box_scores_{year}.pkl'
    if os.path.exists(os.path.join(app.config['CACHE_FOLDER'], cache_file)):
        return load_cached_data(cache_file)
    
    league = League(league_id=league_id, year=year, swid=swid, espn_s2=espn_s2)
    data = []
    for week in weeks:
        box_scores = league.box_scores(week=week)
        for box_score in box_scores:
            home_team = box_score.home_team
            away_team = box_score.away_team
            home_owners = ', '.join([f"{owner['firstName']} {owner['lastName']}" for owner in home_team.owners]) if home_team.owners else "N/A"
            away_owners = ', '.join([f"{owner['firstName']} {owner['lastName']}" for owner in away_team.owners]) if away_team.owners else "N/A"
            data.append({
                'year': year,
                'week': week,
                'home_owners': home_owners,
                'home_score': box_score.home_score,
                'away_owners': away_owners,
                'away_score': box_score.away_score
            })
    df = pd.DataFrame(data)
    cache_data(df, cache_file)
    return replace_names(df)

def get_teams_data(league_id, swid, espn_s2, year):
    cache_file = f'teams_data_{year}.pkl'
    if os.path.exists(os.path.join(app.config['CACHE_FOLDER'], cache_file)):
        return load_cached_data(cache_file)
    
    league = League(league_id=league_id, year=year, swid=swid, espn_s2=espn_s2)
    team_data = []
    for team in league.teams:
        owners = team.owners
        owner_names = ', '.join([f"{owner['firstName']} {owner['lastName']}" for owner in owners]) if owners else "N/A"
        team_data.append({
            'year': year,
            'owners': owner_names,
            'division_name': team.division_name,
            'wins': team.wins,
            'losses': team.losses,
            'points_for': team.points_for,
            'points_against': team.points_against,
            'acquisitions': team.acquisitions,
            'drops': team.drops,
            'trades': team.trades
        })
    teams_df = pd.DataFrame(team_data)
    teams_df = replace_names(teams_df)
    cache_data(teams_df, cache_file)
    return teams_df

def get_all_teams_data(league_id, swid, espn_s2, years):
    all_teams_df = pd.DataFrame()
    for year in years:
        teams_df = get_teams_data(league_id, swid, espn_s2, year)
        all_teams_df = pd.concat([all_teams_df, teams_df], ignore_index=True)
    return all_teams_df

def get_head_to_head_records(league_id, swid, espn_s2, years):
    all_box_scores = pd.DataFrame()
    weeks = range(1, 19)
    for year in years:
        box_scores = get_box_scores(league_id, swid, espn_s2, year, weeks)
        all_box_scores = pd.concat([all_box_scores, box_scores], ignore_index=True)
    
    records = {}
    for index, row in all_box_scores.iterrows():
        home = row['home_owners']
        away = row['away_owners']
        home_score = row['home_score']
        away_score = row['away_score']
        
        if home not in records:
            records[home] = {}
        if away not in records:
            records[away] = {}
        
        if away not in records[home]:
            records[home][away] = {'wins': 0, 'losses': 0}
        if home not in records[away]:
            records[away][home] = {'wins': 0, 'losses': 0}
        
        if home_score > away_score:
            records[home][away]['wins'] += 1
            records[away][home]['losses'] += 1
        else:
            records[away][home]['wins'] += 1
            records[home][away]['losses'] += 1

    records_df = pd.DataFrame.from_dict({(i,j): records[i][j] 
                                         for i in records.keys() 
                                         for j in records[i].keys()},
                                        orient='index')
    records_df.index = pd.MultiIndex.from_tuples(records_df.index, names=['Owner', 'Opponent'])
    records_df.reset_index(inplace=True)
    return replace_names(records_df)

@app.route('/')
def home():
    years = range(2019, 2024)
    league_id = 169486
    swid = '{9D7CB084-B793-4CDB-B037-52F4D98ACC1C}'
    espn_s2 = 'AEBnf8ht3Oh0xvAhRtuyyIu5VpvAehSmKj1wrehc8SlmvaOFPje8AfZuMV79MrraWZ%2B5bJA%2FMxLZLakCKg8sm6jixwPSGpMjHqI28KwjOS4ottSwpPEGZiEHZQAMfs34uX0Le%2BCpz0Z4ztfzPYyqKzGoL5vo%2FgiCDr3TXn57v%2FQj0Wv2gTpv2GMoUMi5WA85b1IFPmD1eEAc5Ifq753KrQruc6TF4dugjFBMNfBO3N70wm3OkozT9ycrA2lhHYafaIap8uR%2Bri%2B7fb2qk56Hz%2F6r'
    owners = get_all_owners(league_id, swid, espn_s2, years)
    return render_template('index.html', years=years, owners=owners)

@app.route('/box_scores', methods=['GET', 'POST'])
def box_scores():
    league_id = 169486
    swid = '{9D7CB084-B793-4CDB-B037-52F4D98ACC1C}'
    espn_s2 = 'AEBnf8ht3Oh0xvAhRtuyyIu5VpvAehSmKj1wrehc8SlmvaOFPje8AfZuMV79MrraWZ%2B5bJA%2FMxLZLakCKg8sm6jixwPSGpMjHqI28KwjOS4ottSwpPEGZiEHZQAMfs34uX0Le%2BCpz0Z4ztfzPYyqKzGoL5vo%2FgiCDr3TXn57v%2FQj0Wv2gTpv2GMoUMi5WA85b1IFPmD1eEAc5Ifq753KrQruc6TF4dugjFBMNfBO3N70wm3OkozT9ycrA2lhHYafaIap8uR%2Bri%2B7fb2qk56Hz%2F6r'
    weeks = range(1, 19)

    if request.method == 'POST':
        year = int(request.form['year'])
        years = [year]
    else:
        years = range(2019, 2024)

    all_years_df = pd.DataFrame()
    for year in years:
        year_df = get_box_scores(league_id, swid, espn_s2, year, weeks)
        year_df = replace_names(year_df)
        all_years_df = pd.concat([all_years_df, year_df], ignore_index=True)

    return render_template('box_scores.html', tables=[all_years_df.to_html(classes='data', index=False)], titles=all_years_df.columns.values, years=years)

@app.route('/teams', methods=['GET', 'POST'])
def teams():
    league_id = 169486
    swid = '{9D7CB084-B793-4CDB-B037-52F4D98ACC1C}'
    espn_s2 = 'AEBnf8ht3Oh0xvAhRtuyyIu5VpvAehSmKj1wrehc8SlmvaOFPje8AfZuMV79MrraWZ%2B5bJA%2FMxLZLakCKg8sm6jixwPSGpMjHqI28KwjOS4ottSwpPEGZiEHZQAMfs34uX0Le%2BCpz0Z4ztfzPYyqKzGoL5vo%2FgiCDr3TXn57v%2FQj0Wv2gTpv2GMoUMi5WA85b1IFPmD1eEAc5Ifq753KrQruc6TF4dugjFBMNfBO3N70wm3OkozT9ycrA2lhHYafaIap8uR%2Bri%2B7fb2qk56Hz%2F6r'

    if request.method == 'POST':
        year = int(request.form['year'])
    else:
        year = 2023  # default year if no year is selected

    teams_df = get_teams_data(league_id, swid, espn_s2, year)
    teams_df = replace_names(teams_df)

    return render_template('teams.html', tables=[teams_df.to_html(classes='data', index=False)], titles=teams_df.columns.values)

@app.route('/records')
def records():
    league_id = 169486
    swid = '{9D7CB084-B793-4CDB-B037-52F4D98ACC1C}'
    espn_s2 = 'AEBnf8ht3Oh0xvAhRtuyyIu5VpvAehSmKj1wrehc8SlmvaOFPje8AfZuMV79MrraWZ%2B5bJA%2FMxLZLakCKg8sm6jixwPSGpMjHqI28KwjOS4ottSwpPEGZiEHZQAMfs34uX0Le%2BCpz0Z4ztfzPYyqKzGoL5vo%2FgiCDr3TXn57v%2FQj0Wv2gTpv2GMoUMi5WA85b1IFPmD1eEAc5Ifq753KrQruc6TF4dugjFBMNfBO3N70wm3OkozT9ycrA2lhHYafaIap8uR%2Bri%2B7fb2qk56Hz%2F6r'
    years = range(2019, 2024)

    all_teams_df = get_all_teams_data(league_id, swid, espn_s2, years)
    all_teams_df = replace_names(all_teams_df)
    
    # Get box scores data to calculate highest and lowest week scores
    all_box_scores = pd.DataFrame()
    weeks = range(1, 19)
    for year in years:
        box_scores = get_box_scores(league_id, swid, espn_s2, year, weeks)
        all_box_scores = pd.concat([all_box_scores, box_scores], ignore_index=True)
    
    highest_week_score = all_box_scores.loc[all_box_scores[['home_score', 'away_score']].idxmax().max()][['home_score', 'home_owners', 'year', 'week']]
    lowest_week_score = all_box_scores.loc[all_box_scores[['home_score', 'away_score']].idxmin().min()][['home_score', 'home_owners', 'year', 'week']]
    
    if highest_week_score['home_score'] < all_box_scores['away_score'].max():
        highest_week_score = all_box_scores.loc[all_box_scores['away_score'].idxmax()][['away_score', 'away_owners', 'year', 'week']]
        highest_week_score.rename({'away_score': 'score', 'away_owners': 'owners'}, inplace=True)
    else:
        highest_week_score.rename({'home_score': 'score', 'home_owners': 'owners'}, inplace=True)
    
    if lowest_week_score['home_score'] > all_box_scores['away_score'].min():
        lowest_week_score = all_box_scores.loc[all_box_scores['away_score'].idxmin()][['away_score', 'away_owners', 'year', 'week']]
        lowest_week_score.rename({'away_score': 'score', 'away_owners': 'owners'}, inplace=True)
    else:
        lowest_week_score.rename({'home_score': 'score', 'home_owners': 'owners'}, inplace=True)

    records = {
        'max_points_for': all_teams_df.loc[all_teams_df['points_for'].idxmax()][['points_for', 'owners', 'year']],
        'min_points_for': all_teams_df.loc[all_teams_df['points_for'].idxmin()][['points_for', 'owners', 'year']],
        'max_points_against': all_teams_df.loc[all_teams_df['points_against'].idxmax()][['points_against', 'owners', 'year']],
        'min_points_against': all_teams_df.loc[all_teams_df['points_against'].idxmin()][['points_against', 'owners', 'year']],
        'max_wins': all_teams_df.loc[all_teams_df['wins'].idxmax()][['wins', 'owners', 'year']],
        'min_wins': all_teams_df.loc[all_teams_df['wins'].idxmin()][['wins', 'owners', 'year']],
        'max_losses': all_teams_df.loc[all_teams_df['losses'].idxmax()][['losses', 'owners', 'year']],
        'min_losses': all_teams_df.loc[all_teams_df['losses'].idxmin()][['losses', 'owners', 'year']],
        'max_acquisitions': all_teams_df.loc[all_teams_df['acquisitions'].idxmax()][['acquisitions', 'owners', 'year']],
        'min_acquisitions': all_teams_df.loc[all_teams_df['acquisitions'].idxmin()][['acquisitions', 'owners', 'year']],
        'max_drops': all_teams_df.loc[all_teams_df['drops'].idxmax()][['drops', 'owners', 'year']],
        'min_drops': all_teams_df.loc[all_teams_df['drops'].idxmin()][['drops', 'owners', 'year']],
        'max_trades': all_teams_df.loc[all_teams_df['trades'].idxmax()][['trades', 'owners', 'year']],
        'min_trades': all_teams_df.loc[all_teams_df['trades'].idxmin()][['trades', 'owners', 'year']],
        'highest_week_score': highest_week_score,
        'lowest_week_score': lowest_week_score
    }

    return render_template('records.html', records=records)

@app.route('/head_to_head', methods=['GET', 'POST'])
def head_to_head():
    league_id = 169486
    swid = '{9D7CB084-B793-4CDB-B037-52F4D98ACC1C}'
    espn_s2 = 'AEBnf8ht3Oh0xvAhRtuyyIu5VpvAehSmKj1wrehc8SlmvaOFPje8AfZuMV79MrraWZ%2B5bJA%2FMxLZLakCKg8sm6jixwPSGpMjHqI28KwjOS4ottSwpPEGZiEHZQAMfs34uX0Le%2BCpz0Z4ztfzPYyqKzGoL5vo%2FgiCDr3TXn57v%2FQj0Wv2gTpv2GMoUMi5WA85b1IFPmD1eEAc5Ifq753KrQruc6TF4dugjFBMNfBO3N70wm3OkozT9ycrA2lhHYafaIap8uR%2Bri%2B7fb2qk56Hz%2F6r'
    years = range(2019, 2024)

    if request.method == 'POST':
        selected_owner = request.form['owner']
        head_to_head_df = get_head_to_head_records(league_id, swid, espn_s2, years)
        head_to_head_df = head_to_head_df[head_to_head_df['Owner'] == selected_owner]
        head_to_head_df = replace_names(head_to_head_df)
    else:
        head_to_head_df = pd.DataFrame()

    owners = get_all_owners(league_id, swid, espn_s2, years)

    return render_template('head_to_head.html', tables=[head_to_head_df.to_html(classes='data', index=False)], titles=head_to_head_df.columns.values, owners=owners)

@app.route('/draft_data', methods=['GET', 'POST'])
def draft_data():
    years = range(2019, 2024)
    df = read_csv_files()
    
    if request.method == 'POST':
        selected_year = request.form['year']
        if selected_year:
            df = df[df['Year'] == int(selected_year)]
            tables = [df.to_html(classes='data', index=False)]
        else:
            tables = []
    else:
        tables = []
    
    return render_template('draft_data.html', tables=tables, years=years)

def get_all_owners(league_id, swid, espn_s2, years):
    all_teams_df = get_all_teams_data(league_id, swid, espn_s2, years)
    owners = set()
    for owners_list in all_teams_df['owners']:
        if owners_list != "N/A":
            for owner in owners_list.split(', '):
                owners.add(owner)
    return sorted(owners)

if __name__ == '__main__':
    app.run(debug=True)
