#! /bin/bash -e
set -o pipefail

cd $(dirname $0)
. ./opensky-credentials.sh

airport='LFBD' # Bordeaux Merignac
latlong_range='44\.[789].*/-0\.' # ignore trajectory not matching 44.[789]/-0.
altitude_max=2500 # ignore trajectory above 2500m

curl_opts='--silent --max-time 99'

ago=${1:-2} # first parameter, default to 2 days ago
begin=$(date -d "-$ago day 00:00" '+%s')
end=$(date -d "-$(($ago - 1)) day 00:00" '+%s')

file_path() # <prefix>
{
	date -d "-$ago day" "+suivi/%Y/%m/%d/$1-%F"
}

mkdir -p $(dirname $(file_path))
file_flights=$(file_path 'opensky-mouvements').csv
file_flight_prefix=$(file_path 'opensky-vol')-
file_summary=$(file_path 'synthese').csv

start_filing() # <message> <file>
{
	trap "rm -f $2" EXIT
	trap "rm -f $2"' ; trap - INT ; kill -s INT $$' INT
	printf '%s for %s ... ' "$1" "$2"
}

continue_filing() # <message> <file>
{
	echo 'OK'
	printf '%s for %s ... ' "$1" "$2"
}

stop_filing()
{
	echo 'OK'
	trap - INT EXIT
}

# OpenSky Network collects air traffic control data
# from 1090 MHz Mode S, ADS-B, FLARM, and VHF/Voice,
# providing both raw transponder data and high-level tracking information.
# It can infer flight origin and destination
# but does not track commercial schedules, cancellations, delays, or passenger counts.
# Flights are updated by a batch process at night,
# i.e., only flights from the previous day or earlier are available.
# Coverage is best in Europe and the US, with no data before 2013.
api_name='opensky-network'
api_domain="$api_name.org"
api_base="https://$api_domain/api"
api_auth="https://auth.$api_domain/auth/realms/$api_name/protocol/openid-connect/token"

token=
auth()
{
	[ -z "$token" ] || return 0
	printf 'Authenticating in %s... ' $api_name
	token=$(curl $curl_opts $api_auth \
		-H "Content-Type: application/x-www-form-urlencoded" \
		-d "grant_type=client_credentials" \
		-d "client_id=$CLIENT_ID" \
		-d "client_secret=$CLIENT_SECRET" |
		jq -r '.access_token')
	# The token will expire after 30 minutes.
	auth="Authorization: Bearer $token"
	echo 'OK'
}

get_flights() { # <file>
	auth
	api_filter="airport=$airport&begin=$begin&end=$end"
	fields='.icao24, .callsign, .estDepartureAirport, .estArrivalAirport, .firstSeen, .lastSeen'
	start_filing 'Requesting departures' $1
	curl $curl_opts -H "$auth" "$api_base/flights/departure?$api_filter" |
	jq -r '.[] | ['"$fields"', "d"] | @csv' |
	sed 's/, *,/,"?   ",/g' > $1
	continue_filing 'Requesting arrivals' $1
	curl $curl_opts -H "$auth" "$api_base/flights/arrival?$api_filter" |
	jq -r '.[] | ['"$fields"', "a"] | @csv' |
	sed 's/, *,/,"?   ",/g' >> $1
	stop_filing
}

get_flight() { # <aircraft> <callsign> <depairport> <arrairport> <deptime> <arrtime> <ad>
	if [ "$7" = 'd' ] ; then
		going='d' # departure
		hourmin=$(date -d @$5 '+%H-%M')
	elif [ "$7" = 'a' ] ; then
		going='a' # arrival
		hourmin=$(date -d @$6 '+%H-%M')
	else
		continue
	fi
	file_flight=$file_flight_prefix$hourmin-$1-$going.csv
	if [ ! -e $file_flight ] ; then
		auth
		fields='[.[0, 1, 2, 3, 4]]' # [time, latitude, longitude, altitude, orientation]
		start_filing 'Requesting trajectory' $file_flight
		curl $curl_opts -H "$auth" "$api_base/tracks/all?icao24=$1&time=$5" |
		jq -r ".path | .[] | $fields | @csv" |
		sort -t',' -k1 |
		while read point ; do
			set -- $(echo $point | sed 's/, *,/,0,/g' | tr ',' ' ')
			# filter on latitude/longitude around airport
			echo $2/$3 | grep -q "$latlong_range" || continue
			# filter on altitude threshold
			if [ $going = 'd' ] ; then
				[ $4 -lt $altitude_max ] || break
				echo "$point"
			elif [ $going = 'a' ] ; then
				[ $4 -lt $altitude_max ] || continue
				echo "$point"
			fi
		done > $file_flight
		stop_filing
	fi
}

if [ ! -e $file_flights ] ; then
	get_flights $file_flights
fi

while read flight ; do
	get_flight $(echo $flight | sed 's,[" ],,g' | tr ',' ' ')
done < $file_flights
