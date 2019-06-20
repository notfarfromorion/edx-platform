""" Management command to create an ApiAccessRequest for given users """
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.contrib.sites.models import Site

from openedx.core.djangoapps.api_admin.models import (
    ApiAccessConfig,
    ApiAccessRequest,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Create an ApiAccessRequest for the given user

    Example usage:
        $ ./manage.py lms create_api_request <username> --create-config
    """

    help = 'Create an ApiAccessRequest for the given user'
    DEFAULT_STATUS = ApiAccessRequest.PENDING
    DEFAULT_WEBSITE = 'www.test-edx-example-website.edu'
    DUMMY_SITE_NAME = 'ApiAccessRequest Management Command Dummy Site'
    DEFAULT_REASON = 'Generated by management job create_api_request'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str)
        parser.add_argument(
            '--create-config',
            action='store_true',
            help='Create ApiAccessConfig if it does not exist'
        )
        parser.add_argument(
            '--status',
            type=str,
            choices=[choice[0] for choice in ApiAccessRequest.STATUS_CHOICES],
            help='Status of the created ApiAccessRequest'
        )
        parser.add_argument(
            '--reason',
            type=str,
            help='Reason of the created ApiAccessRequest'
        )
        parser.add_argument(
            '--website',
            type=str,
            help='Website of the created ApiAccessRequest'
        )
        parser.add_argument(
            '--site-name',
            type=str,
            help='Name of an existing Site that should be associated with this ApiAccessRequest'
        )

    def handle(self, *args, **options):
        user = self.get_user(options.get('username'))
        site = self.get_site(options.get('site_name'))
        self.create_api_access_request(
            user,
            options.get('status'),
            options.get('reason'),
            options.get('website'),
            site,
        )
        if options.get('create_config'):
            self.create_api_access_config()

    def get_user(self, username):
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(u'User {} not found'.format(username))

    def get_site(self, site_name):
        """
        Given a site name, returns the site with that name. If site_name is None, we use
        Site.objects.get_current() which returns the site specified in settings.SITE_ID.
        If a site name is supplied but there is no site found with that name, a CommandError is raised.
        """
        if site_name:
            site = Site.objects.filter(name=site_name).first()
            if site:
                return site
            raise CommandError(u'Site {} not found'.format(site_name))
        else:
            return Site.objects.get_current()

    def create_api_access_request(self, user, status, reason, website, site):
        """
        Creates an ApiAccessRequest with the given values.
        If status, website, or reason are None, default values are used.
        """
        if status is None:
            status = self.DEFAULT_STATUS
        if website is None:
            website = self.DEFAULT_WEBSITE
        if reason is None:
            reason = self.DEFAULT_REASON
        try:
            ApiAccessRequest.objects.create(
                user=user,
                status=status,
                website=website,
                reason=reason,
                site=site,
            )
        except Exception as e:
            msg = u'Unable to create ApiAccessRequest for {}. Exception is {}: {}'.format(
                user.username,
                type(e).__name__,
                e
            )
            raise CommandError(msg)
        logger.info(u'Created ApiAccessRequest for user {}'.format(user.username))

    def create_api_access_config(self):
        """
        Creates an active ApiAccessConfig if one does not currectly exist
        """
        try:
            _, created = ApiAccessConfig.objects.get_or_create(enabled=True)
        except Exception as e:
            msg = u'Unable to create ApiAccessConfig. Exception is {}: {}'.format(type(e).__name__, e)
            raise CommandError(msg)
        if created:
            logger.info(u'Created ApiAccessConfig')
        else:
            logger.info(u'ApiAccessConfig already exists')
