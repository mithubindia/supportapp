The application includes the following features:
- User registration and login with role-based access (user, admin).
- A form for authenticated users to create support tickets, specifying a problem description, priority (Normal, Urgent, Super Urgent), and expected resolution date/time.
- A dashboard for users to view their submitted tickets.
- A comprehensive admin dashboard to view all tickets, approve pending requests, and assign tickets to staff.
- A ticket detail page showing the full history of a ticket, with a commenting system for assigned agents to log actions.
- A reporting page for admins to generate reports on tickets based on filters like date range, status, priority, and user.
- A clean, styled user interface.

The application is configured to use SQLite for portability but can be easily switched to PostgreSQL by changing the database URI in the configuration.

## Running with Docker

To run the application using Docker, make sure you have Docker and Docker Compose installed. Then, follow these steps:

1.  **Build and run the container:**
    ```bash
    docker-compose up --build
    ```
2.  **Access the application:**
    Open your web browser and go to `http://localhost:5000`.

The application will be running in a Docker container, and the database will be persisted in a Docker volume named `support_db`.
