from email.mime.text import MIMEText
import smtplib

import requests


def _get_ip():
    r = requests.get('http://ifconfig.co/ip')
    r.raise_for_status()
    return r.text.strip()


def _save_ip(ip_file, ip):
    with open(ip_file, 'w') as f:
        f.write(ip)


def main(config, ip_file):
    """Check to see if the IP address of this server has changed.
    """
    logging_email = config.logging_email
    s = smtplib.SMTP(logging_email.server_address, logging_email.server_port)
    s.starttls()
    s.login(logging_email.from_address, logging_email.password)

    try:
        with open(ip_file) as f:
            ip = f.read()
    except FileNotFoundError:
        while True:
            try:
                ip = _get_ip()
                break
            except requests.HTTPError as e:
                if e.response.status_code != 429:
                    raise
                return

        _save_ip(ip_file, ip)
        return

    try:
        new_ip = _get_ip()
    except requests.HTTPError as e:
        if e.response.status_code != 429:
            raise
        # don't overload ifconfig.co's servers
        return

    if new_ip != ip:
        text = f'Combine server IP address changed to: {new_ip}'
        msg = MIMEText(text)
        msg['To'] = logging_email.to_address
        msg['From'] = logging_email.from_address
        msg['Subject'] = text
        s.send_message(msg)
        _save_ip(ip_file, new_ip)
