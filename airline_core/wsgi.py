"""
WSGI config for airline_core project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import logging
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'airline_core.settings')

application = get_wsgi_application()

# Ensure database tables exist and are seeded upon application startup
try:
    from django.core.management import call_command
    from resolution_agent.models import Customer
    if Customer.objects.count() == 0:
        call_command('migrate', interactive=False)
        call_command('seed_assignment_data')
except Exception as e:
    try:
        from django.core.management import call_command
        call_command('migrate', interactive=False)
        call_command('seed_assignment_data')
    except Exception as inner_e:
        logging.getLogger('airline_core').exception("Auto-migration on startup failed: %s", inner_e)

