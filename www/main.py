import flask
import pathlib
import csv
import operator
import datetime
import zoneinfo


app = flask.Flask(__name__)
#app.config['DEBUG'] = True
root_dir = pathlib.Path('/var/www/aeroport/suivi')
airport = 'LFBD'
pistes = ((44.82, -0.73), (44.838, -0.7))
pellegrin = ((44.81, -0.62), (44.84, -0.59))
hautleveque = ((44.77, -0.67), (44.80, -0.65))
track_devi_max = 20 # degrees limit + or - for track detection
tz = zoneinfo.ZoneInfo("Europe/Paris")


def in_area(area, waypoint):
	return (
		waypoint[1] > area[0][0] and
		waypoint[2] > area[0][1] and
		waypoint[1] < area[1][0] and
		waypoint[2] < area[1][1]
	)


class CSVReader(csv.DictReader):

	def __init__(self, file, fieldnames):
		dialect = csv.unix_dialect
		dialect.quoting = csv.QUOTE_NONNUMERIC
		super().__init__(file, fieldnames=fieldnames, dialect=dialect)


def get_day_flights(directory):
	flights = []

	for flights_file in directory.glob('opensky-mouvements-*.csv'):
		with open(flights_file, newline='') as flights_file_stream:
			fields = [
				'aircraft',
				'callsign',
				'departure_airport',
				'arrival_airport',
				'departure_time',
				'arrival_time',
				'ad'
			]
			flights_reader = CSVReader(flights_file_stream, fields)
			for flights_row in flights_reader:
				if flights_row['ad'] == 'd':
					departure = ''
					arrival = flights_row['arrival_airport']
					time = flights_row['departure_time']
				elif flights_row['ad'] == 'a':
					departure = flights_row['departure_airport']
					arrival = ''
					time = flights_row['arrival_time']
				else:
					continue

				local = datetime.datetime.fromtimestamp(time, tz)
				localdate = local.strftime('%Y-%m-%d')
				localtime = local.strftime('%H:%M')

				trajectory = get_trajectory(directory, local, flights_row['aircraft'], flights_row['ad'])
				(track, track_orientation, track_name) = get_track(trajectory, flights_row['ad'], flights_row['callsign'])

				flight = [
					flights_row['callsign'],
					departure,
					int(time),
					localdate,
					localtime,
					arrival,
					track_orientation,
					track_name,
					trajectory,
					flights_row['ad']
				]
				flights.append(flight)

	return flights


def get_trajectory(directory, time, aircraft, ad):
	trajectory = []
	hourmin = time.strftime('%H-%M')

	filename = 'opensky-vol-*-%s-%s-%s.csv' % (hourmin, aircraft, ad)
	files = list(directory.glob(filename))
	if not files:
		# fallback to filename without time
		filename = 'opensky-vol-*-%s-%s.csv' % (aircraft, ad)
		files = directory.glob(filename)

	for flight_file in files:
		with open(flight_file, newline='') as flight_file_stream:
			fields = [
				'time',
				'latitude',
				'longitude',
				'altitude',
				'orientation'
			]
			flight_reader = CSVReader(flight_file_stream, fields)
			for flight_row in flight_reader:
				waypoint = [
					flight_row['time'],
					flight_row['latitude'],
					flight_row['longitude'],
					flight_row['altitude'],
					flight_row['orientation']
				]
				trajectory.append(waypoint)

	# sort waypoints by time
	trajectory.sort(key=operator.itemgetter(0))

	return trajectory


def get_track(trajectory, ad, callsign):
	orientation = 0
	track = '?'
	track_name = '?'

	waypoints = []
	if ad == 'd':
		waypoints = trajectory
	elif ad == 'a':
		waypoints = trajectory[::-1]

	if not waypoints:
		return ('?', '?', '?')

	if in_area(pellegrin, waypoints[0]) or in_area(hautleveque, waypoints[0]):
		return ('H', orientation, 'H')
	if callsign[:4] == 'SAMU':
		return ('H', orientation, 'H')
	if callsign[:5] == 'DRAGO':
		return ('H', orientation, 'H')

	non_zero_count = 0
	high_altitude = False
	for waypoint in waypoints:
		if not orientation and not in_area(pistes, waypoint):
			orientation = waypoint[4]
		if waypoint[3] == 0:
			continue
		if non_zero_count == 0: # first non-zero
			first_altitude = waypoint[3]
		if waypoint[3] == first_altitude:
			non_zero_count = non_zero_count + 1
		if waypoint[3] > 999:
			high_altitude = True
			break
	if not orientation:
		if non_zero_count > 5: # slow move: report has many fake altitude at 0
			orientation = waypoints[0][4] # take first point (hope is not taxi)
		else:
			for waypoint in waypoints:
				if waypoint[3] > 0: # filter on altitude to skip taxi
					orientation = waypoint[4]
					break

	if orientation < (45 - track_devi_max):
		track_orientation = orientation
	elif orientation < (45 + track_devi_max):
		track_orientation = '05 (NE)' # 45°
	elif orientation < (106 - track_devi_max):
		track_orientation = orientation
	elif orientation < (106 + track_devi_max):
		track_orientation = '11 (SE)' # 106°
	elif orientation < (225 - track_devi_max):
		track_orientation = orientation
	elif orientation < (225 + track_devi_max):
		track_orientation = '23 (SO)' # 225 °
	elif orientation < (286 - track_devi_max):
		track_orientation = orientation
	elif orientation < (286 + track_devi_max):
		track_orientation = '29 (NO)' # 286°
	else:
		track_orientation = orientation

	if isinstance(track_orientation, str):
		track = track_orientation[:2]
		if track == '05' or track == '23':
			track_name = 'principale'
		elif track == '11' or track == '29':
			track_name = 'secondaire'
		ad_prefix = 'ATT' if ad == 'a' else 'DEC'
		track_orientation = ad_prefix + track_orientation

	return (track, track_orientation, track_name)


@app.route('/suivi')
def suivi():
	flights = []

	directory = sorted(list(root_dir.glob('*/*/*')))[-1]
	flights += get_day_flights(directory)

	# sort flights by time in seconds
	flights.sort(key=operator.itemgetter(2))

	return flask.render_template('suivi.html', flights=flights)


if __name__ == '__main__':
	app.run(host='0.0.0.0')
