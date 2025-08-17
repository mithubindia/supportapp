from flask import Flask, render_template, request, redirect, url_for, flash, session, g, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_sessionstore import Session
from flask_session_captcha import FlaskSessionCaptcha
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import functools
import secrets
import string
import os
import pandas as pd
from io import BytesIO

app = Flask(__name__)
# Using SQLite for portability in this environment.
# The original request for PostgreSQL can be re-enabled by changing this URI.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///support.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'a-secret-key-that-you-should-change' # This will be used for session management
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['CAPTCHA_ENABLE'] = True
app.config['CAPTCHA_LENGTH'] = 5
app.config['CAPTCHA_WIDTH'] = 160
app.config['CAPTCHA_HEIGHT'] = 60
app.config['SESSION_TYPE'] = 'sqlalchemy'


# Flask-Mail configuration
app.config['MAIL_SERVER'] = ''
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = ''
app.config['MAIL_PASSWORD'] = ''
app.config['MAIL_DEFAULT_SENDER'] = ''

mail = Mail(app)
db = SQLAlchemy(app)
app.config['SESSION_SQLALCHEMY'] = db
sess = Session(app)
captcha = FlaskSessionCaptcha(app)

# --- Database Models ---

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255))
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    role = db.relationship('Role', backref=db.backref('users', lazy=True))
    tickets = db.relationship('Ticket', foreign_keys='Ticket.user_id', backref='requester', lazy=True)
    assigned_tickets = db.relationship('Ticket', foreign_keys='Ticket.assigned_to_id', backref='assignee', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    problem_description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(50), nullable=False)
    expected_resolution_datetime = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='Pending')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    actions = db.relationship('TicketAction', backref='ticket', lazy='dynamic', cascade="all, delete-orphan")

    # New fields for the ticket submission form
    issue_details = db.Column(db.String(255), nullable=True)
    issue_type = db.Column(db.String(50), nullable=True)
    organization_name = db.Column(db.String(120), nullable=True)
    address = db.Column(db.Text, nullable=True)
    mobile_number = db.Column(db.String(20), nullable=True)
    file_upload = db.Column(db.String(255), nullable=True)
    ticket_number = db.Column(db.String(12), unique=True, nullable=True)

class TicketAction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    author = db.relationship('User')

class SmtpSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_address = db.Column(db.String(120), nullable=False)
    smtp_server = db.Column(db.String(120), nullable=False)
    smtp_port = db.Column(db.Integer, nullable=False)
    use_tls = db.Column(db.Boolean, default=True)
    username = db.Column(db.String(120), nullable=False)
    password = db.Column(db.String(120), nullable=False)


# --- Helper Functions ---

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("You need to be logged in to view this page.", "danger")
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None or g.user.role.name != 'admin':
            flash("You do not have permission to view this page.", "danger")
            return redirect(url_for('index'))
        return view(**kwargs)
    return wrapped_view

def agent_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None or g.user.role.name not in ['agent', 'admin']:
            flash("You do not have permission to view this page.", "danger")
            return redirect(url_for('index'))
        return view(**kwargs)
    return wrapped_view

@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = User.query.get(user_id)


# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=('GET', 'POST'))
def register():
    if g.user:
        return redirect(url_for('index'))
    if request.method == 'POST':
        if not captcha.validate():
            flash("Invalid captcha.", "danger")
            return redirect(url_for('register'))

        email = request.form['email']
        password = request.form['password']
        error = None

        if not captcha.validate():
            error = 'Invalid captcha.'
        elif not email:
            error = 'Email is required.'
        elif not password:
            error = 'Password is required.'
        elif User.query.filter_by(email=email).first() is not None:
            error = f"User with email {email} is already registered."

        if error is None:
            user_role = Role.query.filter_by(name='user').first()
            if user_role is None:
                # This is a fallback in case roles are not created yet
                flash("Default user role not found. Please contact an administrator.", "danger")
                return redirect(url_for('register'))

            new_user = User(email=email, role=user_role)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))

        flash(error, 'danger')

    return render_template('register.html')

@app.route('/login', methods=('GET', 'POST'))
def login():
    if g.user:
        return redirect(url_for('index'))
    if request.method == 'POST':
        if not captcha.validate():
            flash("Invalid captcha.", "danger")
            return redirect(url_for('login'))

        email = request.form['email']
        password = request.form['password']
        error = None
        user = User.query.filter_by(email=email).first()

        if user is None:
            error = 'Incorrect email or password.'
        elif not user.check_password(password):
            error = 'Incorrect email or password.'

        if error is None:
            session.clear()
            session['user_id'] = user.id
            flash('Login successful!', 'success')
            if user.role.name == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role.name == 'agent':
                return redirect(url_for('agent_dashboard'))
            else:
                return redirect(url_for('index'))

        flash(error, 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

def generate_ticket_number(length=12):
    alphabet = string.ascii_letters + string.digits
    while True:
        ticket_number = ''.join(secrets.choice(alphabet) for i in range(length))
        if not Ticket.query.filter_by(ticket_number=ticket_number).first():
            return ticket_number

@app.route('/create_ticket', methods=('GET', 'POST'))
@login_required
def create_ticket():
    print("create_ticket route called")
    if request.method == 'POST':
        print("request.method == 'POST'")
        problem_description = request.form['problem_description']
        priority = request.form['priority']
        expected_resolution_datetime_str = request.form['expected_resolution_datetime']
        issue_details = request.form['issue_details']
        issue_type = request.form['issue_type']
        organization_name = request.form['organization_name']
        address = request.form['address']
        mobile_number = request.form['mobile_number']
        file = request.files['file_upload']

        error = None
        if not problem_description:
            error = 'Problem description is required.'
        elif not priority:
            error = 'Priority is required.'
        elif not expected_resolution_datetime_str:
            error = 'Expected resolution date and time is required.'

        if error is None:
            try:
                # Convert string to datetime object
                expected_resolution_datetime = datetime.fromisoformat(expected_resolution_datetime_str)

                # Handle file upload
                file_path = None
                if file:
                    if not os.path.exists(app.config['UPLOAD_FOLDER']):
                        os.makedirs(app.config['UPLOAD_FOLDER'])
                    filename = file.filename
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)

                new_ticket = Ticket(
                    problem_description=problem_description,
                    priority=priority,
                    expected_resolution_datetime=expected_resolution_datetime,
                    requester=g.user,
                    issue_details=issue_details,
                    issue_type=issue_type,
                    organization_name=organization_name,
                    address=address,
                    mobile_number=mobile_number,
                    file_upload=file_path,
                    ticket_number=generate_ticket_number()
                )
                db.session.add(new_ticket)
                db.session.commit()

                # Send confirmation email
                settings = SmtpSetting.query.first()
                if settings:
                    app.config.update(
                        MAIL_SERVER=settings.smtp_server,
                        MAIL_PORT=settings.smtp_port,
                        MAIL_USE_TLS=settings.use_tls,
                        MAIL_USERNAME=settings.username,
                        MAIL_PASSWORD=settings.password,
                        MAIL_DEFAULT_SENDER=settings.from_address
                    )
                    mail.init_app(app)
                    msg = Message('Support Ticket Created: ' + new_ticket.ticket_number,
                                  recipients=[new_ticket.requester.email])
                    msg.body = f"""
                    Hello {new_ticket.requester.email},

                    Your support ticket has been created successfully.
                    Your ticket number is: {new_ticket.ticket_number}

                    Please use this ticket number for all future communication regarding this issue.

                    Thank you,
                    The Support Team
                    """
                    try:
                        mail.send(msg)
                        flash('Your support ticket has been created successfully! Your ticket number is ' + new_ticket.ticket_number + '. A confirmation email has been sent.', 'success')
                    except Exception as e:
                        flash('Your support ticket has been created, but the confirmation email could not be sent. Please contact an administrator.', 'warning')
                        app.logger.error(f"Failed to send email: {e}")

                else:
                    flash('Your support ticket has been created successfully! Your ticket number is ' + new_ticket.ticket_number + '. Email not sent: SMTP settings not configured.', 'warning')

                return redirect(url_for('index'))
            except ValueError:
                error = "Invalid date and time format."

        flash(error, 'danger')

    return render_template('create_ticket.html')

@app.route('/tickets')
@login_required
def view_tickets():
    tickets = Ticket.query.filter_by(user_id=g.user.id).order_by(Ticket.created_at.desc()).all()
    return render_template('view_tickets.html', tickets=tickets)


# --- Admin Routes ---

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    agent_id = request.args.get('agent_id')
    query = Ticket.query

    if agent_id:
        query = query.filter_by(assigned_to_id=agent_id)

    stats = {
        'total': query.count(),
        'approved': query.filter_by(status='Approved').count(),
        'pending': query.filter_by(status='Pending').count(),
        'resolved': query.filter_by(status='Resolved').count(),
        'closed': query.filter_by(status='Closed').count()
    }

    tickets = query.order_by(Ticket.created_at.desc()).all()
    agent_role = Role.query.filter_by(name='agent').first()
    agents = User.query.filter_by(role=agent_role).all()

    return render_template('admin/dashboard.html', tickets=tickets, stats=stats, agents=agents, selected_agent=agent_id)

@app.route('/admin/ticket/<int:ticket_id>/approve', methods=['POST'])
@admin_required
def approve_ticket(ticket_id):
    ticket = db.get_or_404(Ticket, ticket_id)
    if ticket.status == 'Pending':
        ticket.status = 'Approved'
        db.session.commit()
        flash(f'Ticket #{ticket.id} has been approved.', 'success')
    else:
        flash(f'Ticket #{ticket.id} could not be approved (Status: {ticket.status}).', 'warning')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/manage_agents')
@admin_required
def manage_agents():
    agent_role = Role.query.filter_by(name='agent').first()
    agents = User.query.filter_by(role=agent_role).all()
    return render_template('admin/manage_agents.html', agents=agents)

@app.route('/admin/add_agent', methods=['POST'])
@admin_required
def add_agent():
    name = request.form['name']
    email = request.form['email']
    password = request.form['password']
    error = None

    if not name:
        error = 'Name is required.'
    elif not email:
        error = 'Email is required.'
    elif not password:
        error = 'Password is required.'
    elif User.query.filter_by(email=email).first() is not None:
        error = f"User with email {email} is already registered."

    if error is None:
        agent_role = Role.query.filter_by(name='agent').first()
        if agent_role is None:
            flash("Agent role not found. Please contact an administrator.", "danger")
            return redirect(url_for('manage_agents'))

        new_agent = User(name=name, email=email, role=agent_role)
        new_agent.set_password(password)
        db.session.add(new_agent)
        db.session.commit()
        flash('Agent added successfully!', 'success')
    else:
        flash(error, 'danger')

    return redirect(url_for('manage_agents'))

@app.route('/admin/delete_agent/<int:user_id>', methods=['POST'])
@admin_required
def delete_agent(user_id):
    agent = db.get_or_404(User, user_id)
    if agent.role.name == 'agent':
        # Reassign tickets before deleting agent
        admin_role = Role.query.filter_by(name='admin').first()
        admin_user = User.query.filter_by(role=admin_role).first()
        if admin_user:
            Ticket.query.filter_by(assigned_to_id=agent.id).update({'assigned_to_id': admin_user.id})
            db.session.commit()
        db.session.delete(agent)
        db.session.commit()
        flash('Agent deleted successfully!', 'success')
    else:
        flash('This user is not an agent.', 'danger')
    return redirect(url_for('manage_agents'))

@app.route('/admin/ticket/<int:ticket_id>/assign', methods=['GET', 'POST'])
@admin_required
def assign_ticket(ticket_id):
    ticket = db.get_or_404(Ticket, ticket_id)
    # Allow assigning to admins and agents
    agent_role = Role.query.filter_by(name='agent').first()
    admin_role = Role.query.filter_by(name='admin').first()
    staff_users = User.query.filter(User.role_id.in_([agent_role.id, admin_role.id])).all()

    if request.method == 'POST':
        assignee_id = request.form.get('assignee_id')
        if assignee_id:
            assignee = User.query.get(assignee_id)
            if assignee and assignee.role.name in ['admin', 'agent']:
                ticket.assigned_to_id = assignee.id
                # Optionally, update status when assigned
                if ticket.status in ['Pending', 'Approved']:
                    ticket.status = 'In Progress'
                db.session.commit()
                flash(f'Ticket #{ticket.id} has been assigned to {assignee.email}.', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid assignee selected.', 'danger')
        else:
            flash('No assignee selected.', 'danger')

    return render_template('admin/assign_ticket.html', ticket=ticket, staff_users=staff_users)

# --- Agent Routes ---

@app.route('/agent/dashboard')
@agent_required
def agent_dashboard():
    tickets = Ticket.query.filter_by(assigned_to_id=g.user.id).order_by(Ticket.created_at.desc()).all()
    return render_template('agent/dashboard.html', tickets=tickets)


@app.route('/ticket/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
def ticket_detail(ticket_id):
    ticket = db.get_or_404(Ticket, ticket_id)

    # Authorization check: only requester, assignee, or an admin can view.
    if not (g.user.id == ticket.user_id or g.user.role.name == 'admin' or g.user.id == ticket.assigned_to_id):
        flash("You are not authorized to view this ticket.", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        # Check if the current user is the assignee or an admin, who are the only ones allowed to post.
        if not (g.user.id == ticket.assigned_to_id or g.user.role.name == 'admin'):
            flash("You are not authorized to perform this action.", "danger")
            return redirect(url_for('ticket_detail', ticket_id=ticket.id))

        action_text = request.form.get('action_text')
        new_status = request.form.get('status')

        if not action_text:
            flash("Action text cannot be empty.", "danger")
        else:
            # Add the new action
            new_action = TicketAction(
                ticket_id=ticket.id,
                user_id=g.user.id,
                action_text=action_text
            )
            db.session.add(new_action)

            # Update status if a new one was selected
            if new_status:
                ticket.status = new_status
                if new_status == 'Resolved':
                    # Send resolution email
                    settings = SmtpSetting.query.first()
                    if settings:
                        app.config.update(
                            MAIL_SERVER=settings.smtp_server,
                            MAIL_PORT=settings.smtp_port,
                            MAIL_USE_TLS=settings.use_tls,
                            MAIL_USERNAME=settings.username,
                            MAIL_PASSWORD=settings.password,
                            MAIL_DEFAULT_SENDER=settings.from_address
                        )
                        mail.init_app(app)
                        msg = Message('Your Ticket has been Resolved: ' + ticket.ticket_number,
                                      recipients=[ticket.requester.email])
                        confirmation_url = url_for('confirm_resolution', ticket_id=ticket.id, _external=True)
                        msg.body = f"""
                        Hello {ticket.requester.email},

                        Your support ticket with number {ticket.ticket_number} has been marked as resolved.

                        Please click the following link to confirm the resolution and close the ticket:
                        {confirmation_url}

                        If you are not satisfied with the resolution, please reply to this email.

                        Thank you,
                        The Support Team
                        """
                        try:
                            mail.send(msg)
                            flash('The ticket has been marked as resolved and a confirmation email has been sent to the user.', 'success')
                        except Exception as e:
                            flash('The ticket has been marked as resolved, but the confirmation email could not be sent. Please contact an administrator.', 'warning')
                            app.logger.error(f"Failed to send email: {e}")
                    else:
                        flash('The ticket has been marked as resolved, but a confirmation email could not be sent because SMTP settings are not configured.', 'warning')


            db.session.commit()
            flash("Your update has been added.", "success")
            return redirect(url_for('ticket_detail', ticket_id=ticket.id))

    actions = ticket.actions.order_by(TicketAction.created_at.asc()).all()
    return render_template('ticket_detail.html', ticket=ticket, actions=actions)

@app.route('/confirm_resolution/<int:ticket_id>')
@login_required
def confirm_resolution(ticket_id):
    ticket = db.get_or_404(Ticket, ticket_id)
    if ticket.requester.id != g.user.id:
        flash('You are not authorized to perform this action.', 'danger')
        return redirect(url_for('index'))

    if ticket.status == 'Resolved':
        ticket.status = 'Closed'
        db.session.commit()
        flash('Thank you for confirming the resolution. The ticket has been closed.', 'success')
    else:
        flash('This ticket is not marked as resolved.', 'warning')

    return redirect(url_for('ticket_detail', ticket_id=ticket.id))

@app.route('/admin/smtp_settings', methods=['GET', 'POST'])
@admin_required
def smtp_settings():
    settings = SmtpSetting.query.first()
    if request.method == 'POST':
        if settings:
            db.session.delete(settings)
            db.session.commit()

        new_settings = SmtpSetting(
            from_address=request.form['from_address'],
            smtp_server=request.form['smtp_server'],
            smtp_port=int(request.form['smtp_port']),
            use_tls='use_tls' in request.form,
            username=request.form['username'],
            password=request.form['password']
        )
        db.session.add(new_settings)
        db.session.commit()
        flash('SMTP settings saved successfully!', 'success')
        # Update Flask-Mail config
        app.config.update(
            MAIL_SERVER=new_settings.smtp_server,
            MAIL_PORT=new_settings.smtp_port,
            MAIL_USE_TLS=new_settings.use_tls,
            MAIL_USERNAME=new_settings.username,
            MAIL_PASSWORD=new_settings.password,
            MAIL_DEFAULT_SENDER=new_settings.from_address
        )
        mail.init_app(app)
        return redirect(url_for('smtp_settings'))

    return render_template('admin/smtp_settings.html', settings=settings)

@app.route('/admin/reports')
@admin_required
def reports():
    query = Ticket.query
    filters = request.args.to_dict()

    start_date_str = filters.get('start_date')
    end_date_str = filters.get('end_date')
    priority = filters.get('priority')
    status = filters.get('status')
    user_id = filters.get('user_id')

    if start_date_str:
        try:
            start_date = datetime.fromisoformat(start_date_str)
            query = query.filter(Ticket.created_at >= start_date)
        except ValueError:
            flash("Invalid start date format. Please use YYYY-MM-DD.", "danger")

    if end_date_str:
        try:
            end_date = datetime.fromisoformat(end_date_str)
            # Add one day to make the range inclusive of the end date
            query = query.filter(Ticket.created_at <= end_date + timedelta(days=1))
        except ValueError:
            flash("Invalid end date format. Please use YYYY-MM-DD.", "danger")

    if priority:
        query = query.filter(Ticket.priority == priority)

    if status:
        query = query.filter(Ticket.status == status)

    if user_id:
        query = query.filter(Ticket.user_id == int(user_id))

    filtered_tickets = query.order_by(Ticket.created_at.desc()).all()
    all_users = User.query.order_by(User.email).all()

    return render_template('admin/reports.html',
                           tickets=filtered_tickets,
                           all_users=all_users,
                           filters=filters)

@app.route('/admin/export_reports', methods=['POST'])
@admin_required
def export_reports():
    filters = request.form.to_dict()
    query = Ticket.query

    start_date_str = filters.get('start_date')
    end_date_str = filters.get('end_date')
    priority = filters.get('priority')
    status = filters.get('status')
    user_id = filters.get('user_id')

    if start_date_str:
        try:
            start_date = datetime.fromisoformat(start_date_str)
            query = query.filter(Ticket.created_at >= start_date)
        except ValueError:
            flash("Invalid start date format. Please use YYYY-MM-DD.", "danger")

    if end_date_str:
        try:
            end_date = datetime.fromisoformat(end_date_str)
            # Add one day to make the range inclusive of the end date
            query = query.filter(Ticket.created_at <= end_date + timedelta(days=1))
        except ValueError:
            flash("Invalid end date format. Please use YYYY-MM-DD.", "danger")

    if priority:
        query = query.filter(Ticket.priority == priority)

    if status:
        query = query.filter(Ticket.status == status)

    if user_id:
        query = query.filter(Ticket.user_id == int(user_id))

    filtered_tickets = query.order_by(Ticket.created_at.desc()).all()

    if not filtered_tickets:
        flash("Nil data, no report.", "warning")
        return redirect(url_for('reports'))

    data = []
    for ticket in filtered_tickets:
        data.append({
            'Ticket ID': ticket.id,
            'Ticket Number': ticket.ticket_number,
            'Requester': ticket.requester.email,
            'Problem Description': ticket.problem_description,
            'Priority': ticket.priority,
            'Status': ticket.status,
            'Created At': ticket.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'Assigned To': ticket.assignee.email if ticket.assignee else 'N/A'
        })

    df = pd.DataFrame(data)
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')
    df.to_excel(writer, index=False, sheet_name='Report')
    writer.close()
    output.seek(0)

    return send_file(output, download_name='support_ticket_report.xlsx', as_attachment=True)


# --- Initialization ---

def init_db():
    with app.app_context():
        db.create_all()
        # Create roles if they don't exist
        if Role.query.filter_by(name='admin').first() is None:
            db.session.add(Role(name='admin'))
        if Role.query.filter_by(name='user').first() is None:
            db.session.add(Role(name='user'))
        if Role.query.filter_by(name='agent').first() is None:
            db.session.add(Role(name='agent'))
        db.session.commit()

        # Create a default admin user if one doesn't exist
        if User.query.filter_by(email='admin@example.com').first() is None:
            admin_role = Role.query.filter_by(name='admin').first()
            admin_user = User(email='admin@example.com', role=admin_role)
            admin_user.set_password('admin')
            db.session.add(admin_user)
            db.session.commit()

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
