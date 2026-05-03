from lagom import Container

from domains.claims.services.claim_service import ClaimService
from domains.claims.services.interfaces.iclaim_service import IClaimService
from domains.claims.proxies.claim_service_proxy import ClaimServiceProxy
from repositories.claims.contracts.iclaim_repository import IClaimRepository

container = Container()
container[IClaimRepository] = ClaimServiceProxy
container[IClaimService] = ClaimService
