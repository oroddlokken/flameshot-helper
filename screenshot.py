#!/usr/bin/env python3

import subprocess
import json
import datetime
import os.path
import pprint
import logging
import os

DEFAULT_CONFIG_LOCATION = "~/.config/oroddlokken/flameshot-helper.json"

# create and configure a base logger
formatter = logging.Formatter(fmt='%(asctime)s %(levelname)s %(message)s',
                              datefmt='%Y-%m-%d %H:%M:%S')

handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger('selca')
logger.addHandler(handler)

# don't propagate, otherwise anything at WARNING level or
# above will be repeated by the root logger
logger.propagate = False
logger.setLevel(logging.INFO)


def get_config_location(args):
    path = os.path.expanduser(DEFAULT_CONFIG_LOCATION)

    return path


def create_rsync_cmd(local_path, remote_path):
    cmd = ["rsync",
           "-Pr",
           "--no-R", "--no-implied-dirs",
           "-p", "--chmod=F775",
           local_path, remote_path]

    return cmd


def create_ssh_mkdir_cmd(config, path):
    cmd = [
        "ssh",
        "-i", config["sftp"]["key"],
        "-p", str(config["sftp"]["port"]),
        "{}@{}".format(config["sftp"]["user"], config["sftp"]["host"]),
        "mkdir -p {}".format(path)
    ]

    return cmd


def save_file(raw_data, path):
    with open(path, "wb") as f:
        f.write(raw_data)

    return True


def flameshot():
    cmd = ["flameshot", "gui", "-r"]

    o = subprocess.check_output(cmd)

    return o


def kde_notify(fname, url):
    cmd = ["notify-send", fname, url]

    subprocess.run(cmd)


def kde_set_clipboard(text):
    cmd = ["qdbus",
           "org.kde.klipper",
           "/klipper",
           "setClipboardContents",
           text]

    subprocess.check_output(cmd)


def xdg_open(path):
    cmd = ["xdg-open", path]

    subprocess.check_output(cmd)


def read_config(path):
    path = os.path.expanduser(path)

    with open(path, "r") as f:
        data = json.load(f)

    return data


class ScreenshotPaths(object):
    def __init__(self, config, timestamp):
        self.config = config
        self.dt = timestamp

        self.sftp_enabled = self.config.get("sftp", {}).get("enabled", False)

        if self.sftp_enabled:
            if self.config["sftp"]["directory"][-1] != "/":
                self.config["sftp"]["directory"] = "{}/".format(
                    self.config["sftp"]["directory"])

    @property
    def formatted_relative_path(self):
        t = self.config["fname"]

        relative_path = self.dt.strftime(t)

        return relative_path

    @property
    def relative_dirname(self):
        return os.path.dirname(self.formatted_relative_path)

    @property
    def relative_basename(self):
        return os.path.basename(self.formatted_relative_path)

    @property
    def local_path(self):
        return os.path.join(os.path.expanduser(self.config["directory"]),
                            self.formatted_relative_path)

    @property
    def local_folder(self):
        return os.path.dirname(self.local_path)

    @property
    def remote_directory(self):
        if not self.sftp_enabled:
            return None

        p = os.path.join(self.config["sftp"]
                         ["directory"], self.relative_dirname)

        return p

    @property
    def remote_path(self):
        if not self.sftp_enabled:
            return None

        p = os.path.join(self.remote_directory, self.relative_basename)

        return p

    @property
    def remote_url(self):
        if not self.sftp_enabled:
            return None

        baseurl = self.config["sftp"].get("baseurl", None)

        if not baseurl:
            return None

        url = "{}{}".format(baseurl, self.formatted_relative_path)

        return url

    @property
    def remote_rsync_path(self):
        if not self.sftp_enabled:
            return None

        remote_path = "{}@{}:{}".format(self.config["sftp"]["user"],
                                        self.config["sftp"]["host"],
                                        self.config["sftp"]["directory"])

        remote_path = "{}{}".format(remote_path, self.formatted_relative_path)

        return remote_path


def main(args):
    logger.info("Starting screenshot helper")
    logger.info("Current DE: {}".format(os.environ.get("XDG_CURRENT_DESKTOP",
                                                       None)))

    dt = datetime.datetime.now()
    logger.info("Got datetime object with timestamp {}".format(dt))

    config_location = get_config_location(args)
    logger.info("Config location: {}".format(config_location))

    config = read_config(config_location)
    logger.info("Config: {}".format(pprint.pformat(config)))

    logger.info("Taking screenshot with flameshot")
    raw_data = flameshot()

    paths = ScreenshotPaths(config, dt)

    logger.info("Creating local folder: {}".format(paths.local_folder))
    os.makedirs(paths.local_folder, exist_ok=True)

    logger.info("Saving screenshot to: {}".format(paths.local_path))
    save_file(raw_data, paths.local_path)

    xdg_path = paths.local_path
    notify_summary = paths.relative_basename
    notify_body = paths.local_path

    sftp_enabled = config.get("sftp", {}).get("enabled", False)
    if sftp_enabled:
        logger.info("SFTP upload is enabled, continuing")

        ssh_mkdir_cmd = create_ssh_mkdir_cmd(config, paths.remote_directory)
        logger.info("Remote mkdir command: {}".format(ssh_mkdir_cmd))
        logger.info("Creating remote directory with ssh")
        subprocess.check_output(ssh_mkdir_cmd)

        rsync_cmd = create_rsync_cmd(paths.local_path, paths.remote_rsync_path)
        logger.info("rsync command: {}".format(rsync_cmd))
        logger.info("Uploading screenshot with rsync")
        subprocess.check_output(rsync_cmd)

        if (config["sftp"].get("clipboard", False) and config["sftp"].get("baseurl", False)):
            logger.info("Adding {} to clipboard".format(paths.remote_url))
            kde_set_clipboard(paths.remote_url)

        if config["sftp"].get("baseurl", False):
            xdg_path = paths.remote_url
            notify_body = paths.remote_url
        else:
            xdg_path = None
            notify_body = paths.remote_path

    else:
        logger.info("SFTP upload is not configured.")

    if config.get("notify", False):
        logger.info("Notifying KDE with filename and path/url")
        kde_notify(notify_summary, notify_body)

    if (xdg_path and config.get("open", False)):
        logger.info("Opening {} with xdg-open".format(xdg_path))
        xdg_open(xdg_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Upload screenshots')

    args = parser.parse_args()

    main(args)
