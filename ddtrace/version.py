__all__ = ["version"]

import pkg_resources

try:
    version = pkg_resources.get_distribution(__name__).version
except pkg_resources.DistributionNotFound:
    # package is not installed
    version = None
