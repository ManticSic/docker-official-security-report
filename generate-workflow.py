import argparse
import json
import logging
import urllib3
import jinja2
import requests
import datetime
import re

logging.basicConfig(level=logging.INFO)

repository_api = "https://hub.docker.com/v2/repositories/library"
auth_token = "<PASSWORD>"
page_query = "?page=1&page_size=100"
default_tag = "latest"
regex_datetime_string_has_no_microseconds = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
datetime_format_microseconds = "%Y-%m-%dT%H:%M:%S.%fZ"
datetime_format_no_microseconds = "%Y-%m-%dT%H:%M:%SZ"


def authenticate_at_dockerhub(username, token):
    logging.info(f"Authenticating")
    response = urllib3.request(
        "POST",
        "https://hub.docker.com/v2/users/login",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"username": username, "password": token}),
    )

    if response.status != 200:
        raise "Failed to authenticate at DockerHub"

    return json.loads(response.data)["token"]


def map_repository_list(repository):
    return {
        "name": repository["name"],
        "description": repository["description"],
        "star_count": repository["star_count"],
        "pull_count": repository["pull_count"],
    }


def filter_repository_list(repository):
    # Exclude the scratch repository, you cannot pull it
    if repository["name"] == "scratch":
        return False
    # as no tags
    elif repository["name"] == "opensuse":
        return False
    # no longer readable
    elif repository["name"] == "java":
        return False
    # not available for used architecture
    elif repository["name"] == "clefos":
        return False

    return True


def parse_datetime_string(datetime_string):
    if regex_datetime_string_has_no_microseconds.match(datetime_string):
        datetime_format = datetime_format_no_microseconds
    else:
        datetime_format = datetime_format_microseconds

    return datetime.datetime.strptime(datetime_string, datetime_format)


def get_last_updated_tag(repository):
    tag_list_url = f"{repository_api}/{repository['name']}/tags/{page_query}"
    result = []

    while tag_list_url is not None:
        response = urllib3.request(
            "GET",
            tag_list_url,
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        data = json.loads(response.data.decode('utf-8'))
        tag_list_url = data["next"]
        result = result + data["results"]

    result = sorted(result, key=lambda tag: parse_datetime_string(tag["last_updated"]), reverse=True)

    return result[0]["name"]


def add_tag_to_repository(repository):
    latest_tag_url = f"{repository_api}/{repository['name']}/tags/{default_tag}"
    has_latest_tag = requests.head(latest_tag_url).status_code == 200

    repository["tag"] = default_tag if has_latest_tag else get_last_updated_tag(repository)
    logging.info(f"Add tag {repository['tag']} to {repository['name']}")

    return repository


def fetch_library_repositories():
    logging.info("Start fetching library repositories")
    repository_list_url = f"{repository_api}/{page_query}"
    result = []

    while repository_list_url is not None:
        response = urllib3.request(
            "GET",
            repository_list_url,
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        data = json.loads(response.data.decode('utf-8'))
        repository_list_url = data["next"]
        result = result + list(map(map_repository_list, data["results"]))

    logging.info(f"Fetched {len(result)} repositories")

    result = list(filter(filter_repository_list, result))
    logging.info(f"Reduce repositories to {len(result)} repositories")

    result = [add_tag_to_repository(repository) for repository in result]

    return result


def create_workflow_file(repositories):
    logging.info("Create workflow file")
    template_loader = jinja2.FileSystemLoader(searchpath="./")
    template_env = jinja2.Environment(loader=template_loader)
    template_file = "report-workflow.yml.tmpl"
    template = template_env.get_template(template_file)
    output_text = template.render(repositories=repositories)

    with open(".github/workflows/generate-report.yml", 'w') as f:
        print(output_text, file=f)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--username", required=True)
    parser.add_argument("-t", "--token", required=True)
    args = parser.parse_args()

    auth_token = authenticate_at_dockerhub(args.username, args.token)
    logging.info("Starting workflow")
    repositories = fetch_library_repositories()
    create_workflow_file(repositories)
    logging.info("Finished workflow")

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
