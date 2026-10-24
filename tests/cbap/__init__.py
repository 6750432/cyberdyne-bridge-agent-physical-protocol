import os

# The conformance fixtures use the explicit legacy permissive profile;
# production defaults are default-deny (see test_device_contract/policy).
os.environ.setdefault("CBAP_TEST_MODE", "1")
