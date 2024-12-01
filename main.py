import pandas as pd
import requests
import typer

app = typer.Typer()

# Base URLs and admin credentials for different environments
CONFIG = {
    "deployed": {
        "BASE_URL": "https://api.reservation.nichemagazine.me",
        "ADMIN_EMAIL": "admin@progressiosolutions.com",
        "ADMIN_PASSWORD": "aiYai1Ooheoph2Ph"
    },
    "local": {
        "BASE_URL": "http://127.0.0.1:8090",
        "ADMIN_EMAIL": "admin@progressiosolutions.com",
        "ADMIN_PASSWORD": "aiYai1Ooheoph2Ph"
    }
}

# Initialize selected environment variables
BASE_URL = None
GUEST_COLLECTION_URL = None
PRIMARY_INVITATION_URL = None
SECONDARY_INVITATION_URL = None
AUTH_URL = None
ADMIN_EMAIL = None
ADMIN_PASSWORD = None


# Authenticate and get admin token
def get_admin_token():
    login_response = requests.post(AUTH_URL, json={
        "identity": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })

    if login_response.status_code == 200:
        return login_response.json().get("token")
    else:
        typer.echo("Failed to authenticate as admin.")
        return None


# Function to delete all existing data
def delete_all_data(headers):
    # Helper function to delete all records in a collection with pagination support
    def delete_records(collection_url):
        deleted_count = 0  # Track the number of deleted records

        while True:
            # Fetch a batch of records from the collection
            response = requests.get(collection_url, headers=headers)
            if response.status_code != 200:
                typer.echo(f"Failed to fetch records for deletion from {collection_url}. Status: {response.status_code}")
                break

            # Extract the items (records) from the response
            records = response.json().get("items", [])
            if not records:
                break  # Exit the loop if no more records are found

            # Iterate over each record in the current batch and delete it
            for record in records:
                delete_response = requests.delete(f"{collection_url}/{record['id']}", headers=headers)
                if delete_response.status_code == 204:
                    deleted_count += 1
                else:
                    typer.echo(f"Failed to delete record {record['id']} from {collection_url}. Status: {delete_response.status_code}")

        typer.echo(f"Deleted {deleted_count} records from {collection_url}")

    # Delete records from each collection in the correct order
    typer.echo("Deleting primary invitations...")
    delete_records(PRIMARY_INVITATION_URL)

    typer.echo("Deleting secondary invitations...")
    delete_records(SECONDARY_INVITATION_URL)

    typer.echo("Deleting guests...")
    delete_records(GUEST_COLLECTION_URL)

    typer.echo("All existing data deleted.")


@app.command(name="process-invitations")
def process_invitations(environment: str = typer.Option("local", help="Specify the environment: 'local' or 'deployed'")):
    global BASE_URL, GUEST_COLLECTION_URL, PRIMARY_INVITATION_URL, SECONDARY_INVITATION_URL, AUTH_URL, ADMIN_EMAIL, ADMIN_PASSWORD

    # Load environment configuration
    if environment in CONFIG:
        BASE_URL = CONFIG[environment]["BASE_URL"]
        ADMIN_EMAIL = CONFIG[environment]["ADMIN_EMAIL"]
        ADMIN_PASSWORD = CONFIG[environment]["ADMIN_PASSWORD"]
    else:
        typer.echo("Invalid environment specified. Use 'local' or 'deployed'.")
        return

    # Set up URLs based on selected environment
    GUEST_COLLECTION_URL = f"{BASE_URL}/api/collections/guest/records"
    PRIMARY_INVITATION_URL = f"{BASE_URL}/api/collections/primary_invitation/records"
    SECONDARY_INVITATION_URL = f"{BASE_URL}/api/collections/secondary_invitation/records"
    AUTH_URL = f"{BASE_URL}/api/admins/auth-with-password"

    # Prompt for CSV path
    csv_path = typer.prompt("Enter the path to the CSV file")

    # Ask if existing data should be deleted
    delete_data = typer.confirm("Do you want to delete all existing data and start fresh?", default=False)

    token = get_admin_token()
    if not token:
        return

    headers = {"Authorization": f"Bearer {token}"}

    if delete_data:
        delete_all_data(headers)

    # Load CSV
    df = pd.read_csv(csv_path)

    invitee_links = []
    for _, row in df.iterrows():
        # Normalize gender value to lowercase
        gender = row["gender"].lower()

        # Create guest data
        guest_data = {
            "name": row["name"],
            "email": row["email"],
            "gender": gender,
            "phone": row["phone"],
        }

        # Create guest record
        guest_response = requests.post(GUEST_COLLECTION_URL, headers=headers, json=guest_data)
        if guest_response.status_code != 200:
            typer.echo(f"Failed to create guest for {row['email']}. Status: {guest_response.status_code}, Error: {guest_response.text}")
            continue
        guest_info = guest_response.json()
        guest_id = guest_info["id"]

        # Create primary invitation, linking to guest by guest ID
        primary_invitation_data = {
            "guest": guest_id,  # Link to the guest via the guest ID
            "is_primary": True
        }
        primary_response = requests.post(PRIMARY_INVITATION_URL, headers=headers, json=primary_invitation_data)
        primary_info = primary_response.json()

        if primary_response.status_code != 200:
            typer.echo(f"Failed to create primary invitation for {row['email']}. Skipping this entry.")
            continue

        primary_invitation_id = primary_info["id"]
        primary_url = f"{BASE_URL}/?id={primary_invitation_id}&type=primary_invitation"

        # Prepare invitee entry for output
        invitee_entry = {
            "name": row["name"],
            "email": row["email"],
            "phone": row["phone"],
            "main_link": primary_url
        }

        # Create secondary invitations based on number of plus ones, linking each to the guest
        for i in range(row["plus_ones"]):
            secondary_invitation_data = {
                "guest": guest_id,  # Link to the guest via the guest ID
                "is_primary": False
            }
            secondary_response = requests.post(SECONDARY_INVITATION_URL, headers=headers, json=secondary_invitation_data)
            secondary_info = secondary_response.json()

            if secondary_response.status_code != 200:
                typer.echo(f"Failed to create secondary invitation {i + 1} for {row['email']}.")
                continue

            secondary_invitation_id = secondary_info["id"]
            secondary_url = f"{BASE_URL}/?id={secondary_invitation_id}&type=secondary_invitation"
            invitee_entry[f"plus_one_link_{i + 1}"] = secondary_url

        invitee_links.append(invitee_entry)

    # Generate output CSV
    output_df = pd.DataFrame(invitee_links)
    output_csv_path = "output_invitations.csv"
    output_df.to_csv(output_csv_path, index=False)
    typer.echo(f"Output CSV generated at {output_csv_path}")


if __name__ == "__main__":
    app()
