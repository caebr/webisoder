# webisoder
# Copyright (C) 2006-2015  Stefan Ott
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from decorator import decorator
from deform import Form, ValidationFailure
from datetime import date, timedelta

from pyramid.httpexceptions import HTTPFound
from pyramid.response import Response
from pyramid.security import remember, forget
from pyramid.view import view_config

from sqlalchemy.exc import DBAPIError
from tvdb_api import BaseUI, Tvdb, tvdb_shownotfound

from .models import DBSession, User, Show
from .forms import ProfileForm, PasswordForm

@decorator
def authenticated(func, *args, **kwargs):

	request = args[0]

	if 'user' in request.session:
		return func(*args, **kwargs)
	else:
		return HTTPFound(location=request.route_url('login'))

@view_config(route_name='home', renderer='templates/index.pt')
def index(request):

	if 'user' in request.session:
		return HTTPFound(location=request.route_url('shows'))

	return {}

@view_config(route_name='shows', renderer='templates/shows.pt')
@authenticated
def shows(request):

	uid = request.session.get('user')
	user = DBSession.query(User).get(uid)
	return {'subscribed': user.shows, 'shows': DBSession.query(Show).all()}

@view_config(route_name='episodes', renderer='templates/episodes.pt')
@authenticated
def episodes(request):

	uid = request.session.get('user')
	user = DBSession.query(User).get(uid)

	then = date.today() - timedelta(user.days_back or 0)
	episodes = [e for e in user.episodes if e.airdate >= then]

	return { 'episodes': episodes }

@view_config(route_name='subscribe', renderer='templates/shows.pt')
@authenticated
def subscribe(request):

	show_id = request.POST.get('show')

	if not show_id:
		return { 'error': 'no show specified' }

	if not show_id.isdigit():
		return { 'error': 'illegal show id' }

	show = DBSession.query(Show).get(int(show_id))

	if not show:
		return { 'error': 'no such show' }

	session = request.session
	uid = session.get('user')
	user = DBSession.query(User).get(uid)
	user.shows.append(show)

	session.flash('Successfully subscribed to "%s"' % show.name, 'info')
	return HTTPFound(location=request.route_url('shows'))

@view_config(route_name='unsubscribe', renderer='templates/shows.pt')
@authenticated
def unsubscribe(request):

	show_id = request.POST.get('show')

	if not show_id:
		return { 'error': 'no show specified' }

	if not show_id.isdigit():
		return { 'error': 'illegal show id' }

	show = DBSession.query(Show).get(int(show_id))

	if not show:
		return { 'error': 'no such show' }

	session = request.session
	uid = session.get('user')
	user = DBSession.query(User).get(uid)
	user.shows.remove(show)

	session.flash('Successfully unsubscribed from "%s"' % show.name, 'info')
	return HTTPFound(location=request.route_url('shows'))

@view_config(route_name='login', renderer='templates/login.pt',
							request_method='GET')
def login_get(request):

	return { 'user': None }

@view_config(route_name='login', renderer='templates/login.pt',
					request_method='POST', check_csrf=True)
def login(request):

	name = request.POST.get('user')
	password = request.POST.get('password')

	if not name or not password:
		request.session.flash('Login failed', 'warning')
		return { 'user': None }

	user = DBSession.query(User).get(name)

	if not user:
		request.session.flash('Login failed', 'warning')
		return { 'user': name }

	if user.authenticate(password):
		request.session['user'] = name
		return HTTPFound(location=request.route_url('shows'))

	request.session.flash('Login failed', 'warning')
	return { 'user': name }

@view_config(route_name='search', renderer='templates/search.pt',
							request_method='POST')
@authenticated
def search_post(request):

	search = request.POST.get('search')

	if not search:
		return { 'error': 'search term missing' }

	result = []

	class TVDBSearch(BaseUI):
		def selectSeries(self, allSeries):
			result.extend(allSeries)
			return BaseUI.selectSeries(self, allSeries)

	tv = Tvdb(custom_ui=TVDBSearch)

	try:
		tv[search]
	except tvdb_shownotfound:
		return { 'shows': [], 'search': search }

	return { 'shows': result, 'search': search }

@view_config(route_name='logout', request_method='GET')
@authenticated
def logout(request):

	request.session.clear()
	request.session.flash('Successfully signed out. Goodbye.', 'info')
	return HTTPFound(location=request.route_url('home'))

@view_config(route_name='profile', renderer='templates/profile.pt',
							request_method='GET')
@authenticated
def profile_get(request):

	uid = request.session.get('user')
	user = DBSession.query(User).get(uid)

	return { 'user': user, 'form_errors': {} }

@view_config(route_name='profile', renderer='templates/profile.pt',
							request_method='POST')
@authenticated
def profile_post(request):

	uid = request.session.get('user')
	user = DBSession.query(User).get(uid)

	controls = request.POST.items()
	form = Form(ProfileForm())

	try:
		data = form.validate(controls)
	except ValidationFailure as e:
		request.session.flash('Failed to update profile', 'danger')
		return { 'user': user, 'form_errors': e.error.asdict() }

	user.mail = data.get('email', user.mail)
	user.days_back = data.get('days_back', user.days_back)
	user.date_offset = data.get('date_offset', user.date_offset)
	user.link_format = data.get('link_format', user.link_format)
	user.site_news = data.get('site_news', user.site_news)

	request.session.flash('Your settings have been updated', 'info')
	return HTTPFound(location=request.route_url('profile'))

@view_config(route_name='reset_token', renderer='templates/profile.pt',
							request_method='POST')
@authenticated
def reset_token_post(request):

	uid = request.session.get('user')
	user = DBSession.query(User).get(uid)
	user.reset_token()

	request.session.flash('Your token has been reset', 'info')
	return HTTPFound(location=request.route_url('profile'))

@view_config(route_name='password', renderer='templates/profile.pt',
							request_method='POST')
@authenticated
def password_post(request):

	uid = request.session.get('user')
	user = DBSession.query(User).get(uid)

	controls = request.POST.items()
	form = Form(PasswordForm())

	try:
		data = form.validate(controls)
	except ValidationFailure as e:
		request.session.flash('Password change failed', 'danger')
		return { 'user': user, 'form_errors': e.error.asdict() }

	if not user.authenticate(data.get('current')):

		request.session.flash('Password change failed', 'danger')
		msg = 'Wrong password'
		return { 'user': user, 'form_errors': { 'current': msg } }

	if not data.get('verify') == data.get('new'):

		request.session.flash('Password change failed', 'danger')
		msg = 'Passwords to not match'
		return { 'user': user, 'form_errors': { 'verify': msg } }

	user.password = data.get('new')

	request.session.flash('Your password has been changed', 'info')
	return HTTPFound(location=request.route_url('profile'))

# TODO remove this
@view_config(route_name='setup', renderer='templates/empty.pt',
							request_method='GET')
def setup(request):

	user = User(name='admin')
	user.password = 'admin'
	DBSession.add(user)

	show = Show(id=1, name='show1', url='http://1')
	DBSession.add(show)
	user.shows.append(show)

	DBSession.add(Show(id=2, name='show2', url='http://2'))
	DBSession.add(Show(id=3, name='show3', url='http://3'))

	return { 'message': 'all done' }

conn_err_msg = """\
Pyramid is having a problem using your SQL database.  The problem
might be caused by one of the following things:

1.  You may need to run the "initialize_webisoder_db" script
    to initialize your database tables.  Check your virtual
    environment's "bin" directory for this script and try to run it.

2.  Your database server may not be running.  Check that the
    database server referred to by the "sqlalchemy.url" setting in
    your "development.ini" file is running.

After you fix the problem, please restart the Pyramid application to
try it again.
"""

