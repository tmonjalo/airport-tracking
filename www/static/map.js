let current_flight = null;
const single_line_properties = {'weight': 3, 'opacity': 0.5};

function show_flight(trajectory, ad) {
	clear_flight();
	let properties = single_line_properties;
	if (ad == 'a')
		properties['color'] = 'red';
	else
		properties['color'] = 'blue';
	current_flight = L.polyline(trajectory, properties);
	current_flight.addTo(map);
}

function clear_flight() {
	if (current_flight) {
		map.removeLayer(current_flight);
		current_flight = null;
	}
}
