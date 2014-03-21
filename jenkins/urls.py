from django.conf.urls import patterns, url

from jenkins.views import (
    JenkinsServerDetailView, JenkinsServerJobBuildsIndexView,
    JenkinsServerListView, JobTypeDetailView, NotificationHandlerView)

# TODO Standardise names on either plural_ or singular_
urlpatterns = patterns("",
    # noqa
    url(r"^jobtypes/(?P<pk>\d+)/$", JobTypeDetailView.as_view(),
        name="jobtype_detail"),
    url(r"^notifications/$", NotificationHandlerView.as_view(),
        name="jenkins_notifications"),
    url(r"^servers/$", JenkinsServerListView.as_view(),
        name="jenkinsserver_list"),
    url(r"^servers/(?P<pk>\d+)/$", JenkinsServerDetailView.as_view(),
        name="jenkinsserver_detail"),
    url(r"^servers/(?P<server_pk>\d+)/jobs/(?P<job_pk>\d+)/",
        JenkinsServerJobBuildsIndexView.as_view(),
        name="jenkinsserver_job_builds_index"),
)
