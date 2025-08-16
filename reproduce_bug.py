import requests
import uuid

BASE_URL = "http://127.0.0.1:5000"

def main():
    session = requests.Session()

    # 1. Log in as admin
    print("Logging in as admin...")
    login_data = {'email': 'admin@example.com', 'password': 'admin'}
    response = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=True)
    if "Logout" not in response.text:
        print("Admin login failed!")
        return
    print("Admin login successful.")

    # 2. Create an agent with a unique email
    agent_email = f"agent-{uuid.uuid4()}@example.com"
    print(f"Creating an agent with email: {agent_email}...")
    agent_data = {'email': agent_email, 'password': 'password'}
    response = session.post(f"{BASE_URL}/admin/add_agent", data=agent_data, allow_redirects=True)
    if "Agent added successfully" not in response.text:
        print("Failed to create agent!")
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text}")
        return
    print("Agent created successfully.")

    # 3. Create a ticket
    print("Creating a ticket...")
    ticket_data = {
        'problem_description': 'This is a test ticket.',
        'priority': 'Normal',
        'expected_resolution_datetime': '2025-12-31T23:59'
    }
    response = session.post(f"{BASE_URL}/create_ticket", data=ticket_data, allow_redirects=True)
    if "Your support ticket has been created successfully" not in response.text:
        print("Failed to create ticket!")
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text}")
        return
    print("Ticket created successfully.")

    # I will assume the ticket id is 1 and the agent id is 2
    ticket_id = 1
    agent_id = 2 # admin is 1

    # 4. Assign the ticket to the agent
    print(f"Assigning ticket {ticket_id} to agent {agent_id}...")
    assign_data = {'assignee_id': agent_id}
    response = session.post(f"{BASE_URL}/admin/ticket/{ticket_id}/assign", data=assign_data, allow_redirects=True)
    if "has been assigned" not in response.text:
        print("Failed to assign ticket!")
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text}")
        return
    print("Ticket assigned successfully.")


if __name__ == "__main__":
    main()
