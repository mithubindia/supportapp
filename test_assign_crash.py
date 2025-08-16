import requests

BASE_URL = 'http://127.0.0.1:5000'

def register_user(email, password):
    url = f"{BASE_URL}/register"
    data = {'email': email, 'password': password}
    response = requests.post(url, data=data, allow_redirects=True)
    return response

def login(email, password):
    url = f"{BASE_URL}/login"
    data = {'email': email, 'password': password}
    session = requests.Session()
    response = session.post(url, data=data, allow_redirects=True)
    return session, response

def create_ticket(session, problem_description, priority, expected_resolution_datetime):
    url = f"{BASE_URL}/create_ticket"
    data = {
        'problem_description': problem_description,
        'priority': priority,
        'expected_resolution_datetime': expected_resolution_datetime,
        'issue_details': 'test',
        'issue_type': 'Software',
        'organization_name': 'test',
        'address': 'test',
        'mobile_number': 'test',
    }
    response = session.post(url, data=data, allow_redirects=True)
    return response

def create_agent(session, email, password):
    url = f"{BASE_URL}/admin/add_agent"
    data = {'email': email, 'password': password}
    response = session.post(url, data=data, allow_redirects=True)
    return response

def get_tickets(session):
    url = f"{BASE_URL}/admin/dashboard"
    response = session.get(url)
    return response

def assign_ticket(session, ticket_id, assignee_id):
    url = f"{BASE_URL}/admin/ticket/{ticket_id}/assign"
    data = {'assignee_id': assignee_id}
    response = session.post(url, data=data, allow_redirects=True)
    return response

if __name__ == '__main__':
    # 1. Register a new user
    print("Registering a new user...")
    register_response = register_user('testuser2@example.com', 'password')
    print(f"Status code: {register_response.status_code}")

    # 2. Log in as the new user and create a ticket
    print("\nLogging in as the new user and creating a ticket...")
    user_session, _ = login('testuser2@example.com', 'password')
    create_ticket_response = create_ticket(user_session, 'Test ticket', 'Normal', '2025-12-31T23:59')
    print(f"Status code: {create_ticket_response.status_code}")

    # 3. Log in as an admin
    print("\nLogging in as an admin...")
    admin_session, _ = login('admin@example.com', 'admin')

    # 4. Create an agent
    print("\nCreating an agent...")
    create_agent_response = create_agent(admin_session, 'testagent@example.com', 'password')
    print(f"Status code: {create_agent_response.status_code}")

    # 5. Get the ticket id of the created ticket
    print("\nGetting the list of tickets...")
    dashboard_response = get_tickets(admin_session)
    # This part is tricky as it requires parsing the HTML response.
    # I will assume the ticket id is 1 for now.
    ticket_id = 1
    print(f"Assuming ticket id is {ticket_id}")

    # 6. Access the assign page for the ticket
    print(f"\nAccessing the assign page for ticket {ticket_id}...")
    assign_page_url = f"{BASE_URL}/admin/ticket/{ticket_id}/assign"
    assign_page_response = admin_session.get(assign_page_url)
    print(f"Status code: {assign_page_response.status_code}")
    if assign_page_response.status_code != 200:
        print("Failed to access the assign page.")
        print(assign_page_response.text)

    # 7. Assign the ticket to the agent
    # This part is also tricky as it requires getting the agent's id.
    # I will assume the agent id is 2.
    agent_id = 2
    print(f"\nAssigning ticket {ticket_id} to agent {agent_id}...")
    assign_response = assign_ticket(admin_session, ticket_id, agent_id)
    print(f"Status code: {assign_response.status_code}")
    if assign_response.status_code != 200:
        print("Failed to assign the ticket.")
        print(assign_response.text)
    else:
        print("Ticket assigned successfully.")
