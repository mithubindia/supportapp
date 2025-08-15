from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import functools

app = Flask(__name__)
# Using SQLite for portability in this environment.
# The original request for PostgreSQL can be re-enabled by changing this URI.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///support.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'a-secret-key-that-you-should-change' # This will be used for session management

db = SQLAlchemy(app)

# --- Database Models ---

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
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

class TicketAction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    author = db.relationship('User')


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
        email = request.form['email']
        password = request.form['password']
        error = None

        if not email:
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
            return redirect(url_for('index'))

        flash(error, 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/create_ticket', methods=('GET', 'POST'))
@login_required
def create_ticket():
    if request.method == 'POST':
        problem_description = request.form['problem_description']
        priority = request.form['priority']
        expected_resolution_datetime_str = request.form['expected_resolution_datetime']

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

                new_ticket = Ticket(
                    problem_description=problem_description,
                    priority=priority,
                    expected_resolution_datetime=expected_resolution_datetime,
                    requester=g.user
                )
                db.session.add(new_ticket)
                db.session.commit()
                flash('Your support ticket has been created successfully!', 'success')
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
    tickets = Ticket.query.order_by(Ticket.created_at.desc()).all()
    return render_template('admin/dashboard.html', tickets=tickets)

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

@app.route('/admin/ticket/<int:ticket_id>/assign', methods=['GET', 'POST'])
@admin_required
def assign_ticket(ticket_id):
    ticket = db.get_or_404(Ticket, ticket_id)
    # For now, we'll consider all admins as potential assignees
    admin_role = Role.query.filter_by(name='admin').first()
    staff_users = User.query.filter_by(role=admin_role).all()

    if request.method == 'POST':
        assignee_id = request.form.get('assignee_id')
        if assignee_id:
            assignee = User.query.get(assignee_id)
            if assignee and assignee.role.name == 'admin':
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

@app.route('/ticket/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
def ticket_detail(ticket_id):
    ticket = db.get_or_404(Ticket, ticket_id)

    # Authorization check: only requester or an admin can view.
    if not (g.user.id == ticket.user_id or g.user.role.name == 'admin'):
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

            db.session.commit()
            flash("Your update has been added.", "success")
            return redirect(url_for('ticket_detail', ticket_id=ticket.id))

    actions = ticket.actions.order_by(TicketAction.created_at.asc()).all()
    return render_template('ticket_detail.html', ticket=ticket, actions=actions)

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


# --- Initialization ---

def init_db():
    with app.app_context():
        db.create_all()
        # Create roles if they don't exist
        if Role.query.filter_by(name='admin').first() is None:
            db.session.add(Role(name='admin'))
        if Role.query.filter_by(name='user').first() is None:
            db.session.add(Role(name='user'))
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
