# SignPath Foundation readiness checklist

This checklist tracks PoENavi's preparation for a SignPath Foundation OSS code-signing application. It is not a statement that the project has already been accepted.

## Eligibility

- [x] Public GitHub repository
- [x] PoENavi source code released under the OSI-approved MIT License
- [x] Active project with documentation and public releases
- [x] GitHub multi-factor authentication enabled for the maintainer
- [x] No telemetry, advertising, or operator-controlled collection server
- [x] Privacy and uninstall behavior documented
- [x] Required SignPath attribution included in the code-signing policy
- [x] Authors, reviewers, and signing approvers identified
- [x] Only project-authored executables are proposed for signing
- [x] Each signing request requires manual approval

## Build integrity

- [x] Official build runs on a GitHub-hosted Windows runner
- [x] Release tag is checked against `APP_VERSION`
- [x] Runtime and build Python packages are version-pinned
- [x] Python runtime patch version is pinned in GitHub Actions
- [x] `ProductName`, `ProductVersion`, and `FileVersion` metadata are generated from source configuration
- [x] Existing SHA-256 release checksum remains part of the release process
- [ ] Run the updated workflow on Windows and inspect both executable version resources
- [ ] Add SignPath submission, manual approval, signed-artifact retrieval, and signature verification after acceptance

## Licensing and project scope

- [x] Runtime components and license families are documented in `THIRD_PARTY_NOTICES.md`
- [x] Application draft discloses bundled upstream runtime binaries
- [x] Application draft discloses Path of Exile metadata and user-created map-reference images
- [x] Generate and audit `THIRD_PARTY_LICENSES/` with complete license texts from the exact release environment
- [ ] Ask SignPath Foundation to confirm that non-executable game data does not prevent OSS eligibility

## External actions requiring maintainer review

- [ ] Review and publish the readiness changes
- [ ] Supply a contact email directly to SignPath Foundation
- [ ] Submit the application
- [ ] Enable SignPath MFA and configure the approved project
- [ ] Publish the first signed release only after signature verification succeeds
