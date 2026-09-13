from django.core.mail import send_mail
import requests

def notify_email(subject, message, recipients):
    send_mail(subject, message, "aaron.motari@gmail.com", recipients, fail_silently=True)

def notify_slack(message, webhook_url):
    requests.post(webhook_url, json={"text": message})

def notify_whatsapp(message, number, token):
    requests.post("https://api.whatsapp.com/send", data={"phone": number, "text": message})

def notify_sms(message, phone, twilio_sid, twilio_token):
    # integrate Twilio if you want
    pass