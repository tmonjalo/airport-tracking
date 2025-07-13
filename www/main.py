import flask


app = flask.Flask(__name__)
#app.config['DEBUG'] = True


@app.route('/suivi')
def suivi():
	return flask.render_template('suivi.html')


if __name__ == '__main__':
	app.run(host='0.0.0.0')
