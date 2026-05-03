import ipaddress


def is_local(ip: str) -> bool:
    """Return True for loopback, RFC-1918, and IPv6 private/link-local addresses."""
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_loopback or addr.is_private or addr.is_link_local
    except ValueError:
        return False
