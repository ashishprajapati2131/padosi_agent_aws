from sqlalchemy.orm import Session, selectinload
from app.models.agent import Agent
from app.models.agent_insurance_segment import AgentInsuranceSegment
from app.models.agent_profile import AgentProfile
from app.models.agent_subscription import AgentSubscription
from app.models.agent_serviceable_city import AgentServiceableCity
from app.models.agent_portfolio import AgentPortfolio
from app.models.agent_lead_preference import AgentLeadPreference
from app.models.agent_family_license import AgentFamilyLicense
from app.models.agent_performance_stat import AgentPerformanceStat
from app.models.agent_achievement_photo import AgentAchievementPhoto
from app.models.agent_career_timeline import AgentCareerTimeline
from app.models.agent_service_pincode import AgentServicePincode
from app.models.agent_product_expertise import AgentProductExpertise
from app.models.city import City
from app.models.agent_review import AgentReview

class AgentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> Agent:
        from sqlalchemy import func
        return self.db.query(Agent).filter(func.lower(Agent.email) == func.lower(email)).first()

    def get_by_id(self, agent_id: int) -> Agent:
        return self.db.query(Agent).filter(Agent.id == agent_id).first()

    def get_agent_with_full_profile(self, agent_id: int) -> Agent:
        return self.db.query(Agent).options(
            selectinload(Agent.profile),
            selectinload(Agent.subscriptions),
            selectinload(Agent.insurance_segments),
            selectinload(Agent.product_expertise),
            selectinload(Agent.service_pincodes),
            selectinload(Agent.serviceable_cities).selectinload(AgentServiceableCity.city),
            selectinload(Agent.portfolios),
            selectinload(Agent.lead_preferences),
            selectinload(Agent.family_licenses),
            selectinload(Agent.performance_stats),
            selectinload(Agent.achievement_photos),
            selectinload(Agent.career_timelines)
        ).filter(Agent.id == agent_id).first()

    def create(self, agent: Agent) -> Agent:
        self.db.add(agent)
        self.db.flush()
        return agent

    def update_segments(self, agent_id: int, segments: list[str]):
        # Laravel's logic: delete existing segments and create new ones
        self.db.query(AgentInsuranceSegment).filter(
            AgentInsuranceSegment.agent_id == agent_id
        ).delete(synchronize_session=False)
        
        for segment in segments:
            new_segment = AgentInsuranceSegment(
                agent_id=agent_id,
                segment_type=segment
            )
            self.db.add(new_segment)
        
        self.db.flush()

    def save_location(self, agent_id: int, pincode: str, lat: float, lng: float) -> bool:
        agent = self.get_by_id(agent_id)
        if agent:
            agent.agent_pincode = pincode
            agent.latitude = lat
            agent.longitude = lng
            self.db.flush()
            return True
        return False

    def get_agent_public_profile(self, slug: str) -> Agent:
        query = self.db.query(Agent).options(
            selectinload(Agent.profile),
            selectinload(Agent.subscriptions),
            selectinload(Agent.reviews).selectinload(AgentReview.user),
            selectinload(Agent.performance_stats),
            selectinload(Agent.family_licenses),
            selectinload(Agent.insurance_segments),
            selectinload(Agent.portfolios),
            selectinload(Agent.achievement_photos),
            selectinload(Agent.lead_preferences),
            selectinload(Agent.serviceable_cities).selectinload(AgentServiceableCity.city),
            selectinload(Agent.product_expertise),
            selectinload(Agent.career_timelines)
        )
        
        # Only find by slug via the joined profile
        agent = query.join(AgentProfile, Agent.id == AgentProfile.agent_id).filter(AgentProfile.slug == slug).first()
        return agent
