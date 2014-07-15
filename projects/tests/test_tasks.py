from __future__ import unicode_literals

from django.test import TestCase
from jenkins.models import Build

from projects.helpers import build_project
from projects.models import (
    ProjectDependency, ProjectBuildDependency, ProjectBuild)
from projects.tests.factories import DependencyFactory, ProjectFactory
from projects.tasks import process_build_dependencies
from jenkins.tests.factories import BuildFactory


class ProcessBuildDependenciesTest(TestCase):
    def setUp(self):
        self.project = ProjectFactory.create()

    def create_dependencies(self, count=1):
        """
        Utility function to create projects and dependencies.
        """
        project = ProjectFactory.create()
        dependencies = [project]
        for x in range(count):
            dependency = DependencyFactory.create()
            ProjectDependency.objects.create(
                project=project, dependency=dependency)
            dependencies.append(dependency)
        return dependencies

    def test_auto_track_build(self):
        """
        If we create a new build for a dependency of a Project, and the
        ProjectDependency is set to auto_track then the current_build should be
        updated to reflect the new build.
        """
        build1 = BuildFactory.create()
        dependency = DependencyFactory.create(job=build1.job)

        project_dependency = ProjectDependency.objects.create(
            project=self.project, dependency=dependency)
        project_dependency.current_build = build1
        project_dependency.save()

        build2 = BuildFactory.create(job=build1.job)

        result = process_build_dependencies(build2.pk)

        # Reload the project dependency
        project_dependency = ProjectDependency.objects.get(
            pk=project_dependency.pk)
        self.assertEqual(build2, project_dependency.current_build)
        self.assertEqual(build2.pk, result)

    def test_new_build_with_no_auto_track_build(self):
        """
        If we create a new build for a dependency of a Project, and the
        ProjectDependency is not set to auto_track then the current_build
        should not be updated.
        """
        build1 = BuildFactory.create()
        dependency = DependencyFactory.create(job=build1.job)

        project_dependency = ProjectDependency.objects.create(
            project=self.project, dependency=dependency, auto_track=False)
        project_dependency.current_build = build1
        project_dependency.save()

        build2 = BuildFactory.create(job=build1.job)
        process_build_dependencies(build2.pk)

        # Reload the project dependency
        project_dependency = ProjectDependency.objects.get(
            pk=project_dependency.pk)
        self.assertEqual(build1, project_dependency.current_build)

    def test_projectbuild_updates_when_build_created(self):
        """
        If we have a ProjectBuild with a dependency, which is associated with a
        job, and we get a build from that job, then if the build_id is correct,
        we should associate the build dependency with that build.
        """
        dependency1 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=self.project, dependency=dependency1)

        dependency2 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=self.project, dependency=dependency2)

        projectbuild = build_project(self.project, queue_build=False)

        build1 = BuildFactory.create(
            job=dependency1.job, build_id=projectbuild.build_key)

        process_build_dependencies(build1.pk)

        build_dependencies = ProjectBuildDependency.objects.filter(
            projectbuild=projectbuild)
        self.assertEqual(2, build_dependencies.count())
        dependency = build_dependencies.get(dependency=dependency1)
        self.assertEqual(build1, dependency.build)

        dependency = build_dependencies.get(dependency=dependency2)
        self.assertIsNone(dependency.build)

    def test_project_build_status_when_all_dependencies_have_builds(self):
        """
        When we have FINALIZED builds for all the dependencies, the projectbuild
        state should be FINALIZED.
        """
        dependency1 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=self.project, dependency=dependency1)

        dependency2 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=self.project, dependency=dependency2)

        from projects.helpers import build_project

        projectbuild = build_project(self.project, queue_build=False)

        for job in [dependency1.job, dependency2.job]:
            build = BuildFactory.create(
                job=job, build_id=projectbuild.build_key, phase=Build.FINALIZED)
            process_build_dependencies(build.pk)

        projectbuild = ProjectBuild.objects.get(pk=projectbuild.pk)
        self.assertEqual("SUCCESS", projectbuild.status)
        self.assertEqual(Build.FINALIZED, projectbuild.phase)
        self.assertIsNotNone(projectbuild.ended_at)

    def test_auto_track_dependency_triggers_project_build_creation(self):
        """
        If we record a build of a project dependency that is auto-tracked,
        then this should trigger the creation of a new ProjectBuild for that
        project.
        """
        dependency1 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=self.project, dependency=dependency1)

        dependency2 = DependencyFactory.create()
        existing_build = BuildFactory.create(
            job=dependency2.job, phase=Build.FINALIZED)
        ProjectDependency.objects.create(
            project=self.project, dependency=dependency2,
            current_build=existing_build)

        self.assertEqual(
            0,
            ProjectBuild.objects.filter(project=self.project).count())

        build = BuildFactory.create(job=dependency1.job, phase=Build.FINALIZED)
        process_build_dependencies(build.pk)

        self.assertEqual(
            1,
            ProjectBuild.objects.filter(project=self.project).count())

        projectbuild = ProjectBuild.objects.get(project=self.project)
        self.assertEqual(
            2,
            ProjectBuildDependency.objects.filter(
                projectbuild=projectbuild).count())
        build_dependency1 = ProjectBuildDependency.objects.get(
            projectbuild=projectbuild,
            dependency=dependency1)
        self.assertEqual(build, build_dependency1.build)

        build_dependency2 = ProjectBuildDependency.objects.get(
            projectbuild=projectbuild,
            dependency=dependency2)
        self.assertEqual(existing_build, build_dependency2.build)

    def test_build_with_projectbuild_dependencies(self):
        """
        ProjectBuildDependencies should be tied to the newly created build.
        """
        project1, dependency1, dependency2 = self.create_dependencies(2)
        project2 = ProjectFactory.create()
        ProjectDependency.objects.create(project=project2,
                                         dependency=dependency2)

        projectbuild = build_project(project1, queue_build=False)

        build1 = BuildFactory.create(
            job=dependency1.job, build_id=projectbuild.build_key)
        process_build_dependencies(build1.pk)
        dependencies = ProjectBuildDependency.objects.all().order_by(
            "dependency__name")
        self.assertEqual(
            sorted([dependency1, dependency2], key=lambda x: x.name),
            [b.dependency for b in dependencies])
        self.assertEqual(
            [None, build1], sorted([b.build for b in dependencies]))

    def test_build_with_several_projectbuild_dependencies(self):
        """
        A build of dependency that's autotracked by several projects should
        trigger creation of all projectbuilds correctly.
        """
        project1, dependency = self.create_dependencies()
        project2 = ProjectFactory.create()
        ProjectDependency.objects.create(project=project2,
                                         dependency=dependency)

        projectbuild = build_project(project1, queue_build=False)

        build = BuildFactory.create(
            job=dependency.job, build_id=projectbuild.build_key)

        process_build_dependencies(build.pk)

        self.assertEqual(
            [dependency, dependency],
            sorted([b.dependency for b in
                    ProjectBuildDependency.objects.all()]))
        self.assertEqual(
            [build, build],
            sorted([b.build for b in
                    ProjectBuildDependency.objects.all()]))
