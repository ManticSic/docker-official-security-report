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



def map_image_list(image):
    return {
        "name": image["name"],
        "description": image["description"],
        "star_count": image["star_count"],
        "pull_count": image["pull_count"],
    }


def filter_image_list(image):
    # Exclude the scratch image, you cannot pull it
    if image["name"] == "scratch":
        return False
    # as no tags
    elif image["name"] == "opensuse":
        return False
    # no longer readable
    elif image["name"] == "java":
        return False
    # not available for used architecture
    elif image["name"] == "clefos":
        return False

    return True


def parse_datetime_string(datetime_string):
    if regex_datetime_string_has_no_microseconds.match(datetime_string):
        datetime_format = datetime_format_no_microseconds
    else:
        datetime_format = datetime_format_microseconds

    return datetime.datetime.strptime(datetime_string, datetime_format)


def get_last_updated_tag(image):
    tag_list_url = f"{repository_api}/{image['name']}/tags/{page_query}"
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


def add_tag_to_image(image):
    latest_tag_url = f"{repository_api}/{image['name']}/tags/{default_tag}"
    has_latest_tag = requests.head(latest_tag_url).status_code == 200

    image["tag"] = default_tag if has_latest_tag else get_last_updated_tag(image)
    logging.info(f"Add tag {image['tag']} to {image['name']}")

    return image


def fetch_library_images():
    logging.info("Start fetching library images")
    image_list_url = f"{repository_api}/{page_query}"
    result = []

    while image_list_url is not None:
        response = urllib3.request(
            "GET",
            image_list_url,
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        data = json.loads(response.data.decode('utf-8'))
        image_list_url = data["next"]
        result = result + list(map(map_image_list, data["results"]))

    logging.info(f"Fetched {len(result)} images")

    result = list(filter(filter_image_list, result))
    logging.info(f"Reduce images to {len(result)} images")

    result = [add_tag_to_image(image) for image in result]

    return result


def create_workflow_file(data):
    logging.info("Create workflow file")
    templateLoader = jinja2.FileSystemLoader(searchpath="./")
    templateEnv = jinja2.Environment(loader=templateLoader)
    TEMPLATE_FILE = "report-workflow.yml.tmpl"
    template = templateEnv.get_template(TEMPLATE_FILE)
    outputText = template.render(images=data)

    with open(".github/workflows/generate-report.yml", 'w') as f:
        print(outputText, file=f)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--username", required=True)
    parser.add_argument("-t", "--token", required=True)
    args = parser.parse_args()

    auth_token = authenticate_at_dockerhub(args.username, args.token)
    logging.info("Starting workflow")
    images = fetch_library_images()
    create_workflow_file(images)
    logging.info("Finished workflow")

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
