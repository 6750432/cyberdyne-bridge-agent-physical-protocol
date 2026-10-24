# Contributing / 贡献指南

## License of contributions

By submitting a pull request, patch, issue attachment, or other contribution,
you agree that:

```text
you have the right to submit it
it is licensed under the project's MIT license
you will retain applicable third-party notices
```

Do not submit code you cannot license under these terms.

## Before opening a PR

```bash
python3 tools/cbap_conformance.py --target fake
python3 tools/test_host_desktop.py
python3 tools/test_host_devices.py
```

For host/device changes, also run the relevant safety tests and describe:

```text
what device/action changed
default permission
safe_state
resource limits
whether input/network/filesystem access is involved
```

## Security and privacy

Never commit:

```text
real tokens or private keys
personal logs or diary content
other people's screenshots or data
absolute local paths
production hostnames/IPs
```

Use fixtures, temporary directories, and redacted logs.

## Third-party code

If you add or modify a patch against an upstream project:

```text
record the upstream URL and license
keep the upstream license text
mark GPL/AGPL patches clearly
do not relicense upstream code as MIT
```

See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Style

```text
small, reviewable commits
tests for behavior changes
no hidden network calls
fail closed by default
document security boundaries
```

## Code of conduct

Be direct about technical problems, not hostile to people.  
Harassment, doxxing, and malicious use are not welcome.
