import logging

logger = logging.getLogger(__name__)

class AIPicksService:
    @staticmethod
    def calculate_weighted_score(agent, distance):
        """
        Calculates an overall weighted score (0-100) for an agent based on multiple normalized parameters.
        - User Requirement Match: 25%
        - Distance: 20%
        - Experience: 15%
        - Rating: 10%
        - Reviews Count: 10%
        - Happy Clients: 5%
        - Claims Settled: 5%
        - Verified Licenses: 5%
        - Profile Completeness: 3%
        - Recent Activity / Response Rate: 2%
        """
        try:
            # 1. User Requirement Match (25% weight)
            req_match = float(agent.calculated_match_percent or 80.0)

            # 2. Distance (20% weight)
            # Distance <= 50km is normalized linearly (0km -> 100, 50km -> 0). Default to 0.
            if distance is None or distance == 999999 or distance > 50:
                dist_score = 0.0
            else:
                dist_score = max(0.0, min(100.0, (1.0 - (float(distance) / 50.0)) * 100.0))

            # 3. Experience (15% weight)
            # Normalize experience up to a max reference of 15 years
            exp_years = float(agent.experience_years or 0)
            exp_score = min(100.0, (exp_years / 15.0) * 100.0)

            # 4. Rating (10% weight)
            # Normalize rating (0-5 scale)
            rating = float(agent.average_rating or 0.0)
            rating_score = (rating / 5.0) * 100.0

            # 5. Reviews Count (10% weight)
            # Normalize review count up to a max reference of 50 reviews
            rev_count = float(agent.review_count or 0)
            rev_score = min(100.0, (rev_count / 50.0) * 100.0)

            # 6. Happy Clients (5% weight)
            # Parse client base range/string to float. Reference max = 500 clients.
            try:
                clients = float(agent.client_base or 0)
            except (ValueError, TypeError):
                clients = 0.0
            clients_score = min(100.0, (clients / 500.0) * 100.0)

            # 7. Claims Settled (5% weight)
            # Reference max = 100 claims settled
            perf = getattr(agent, 'performanceStats', None)
            try:
                claims_settled = float(perf.claims_settled) if (perf and perf.claims_settled is not None) else 0.0
            except (ValueError, TypeError):
                claims_settled = 0.0
            claims_score = min(100.0, (claims_settled / 100.0) * 100.0)

            # 8. Verified Licenses (5% weight)
            # 100 if both IRDAI and AMFI credentials are valid/non-empty. 50 if one.
            profile = getattr(agent, 'profile', None)
            has_irdai = bool(profile.license_number) if profile else False
            has_amfi = bool(profile.arn_number) if profile else False
            license_score = 0.0
            if has_irdai and has_amfi:
                license_score = 100.0
            elif has_irdai or has_amfi:
                license_score = 50.0

            # 9. Profile Completeness (3% weight)
            # Calculates completeness dynamically matching agent dashboard logic
            comp_score = 15.0
            if profile:
                if profile.address and profile.languages:
                    comp_score += 15.0
                if getattr(profile, 'service_pincodes', None) and agent.serviceableCities.exists():
                    comp_score += 15.0
                if agent.insuranceSegments.exists():
                    comp_score += 15.0
                if hasattr(agent, 'portfolios') and agent.portfolios.exists():
                    comp_score += 15.0
                if profile.profile_photo_path:
                    comp_score += 10.0
                if hasattr(agent, 'leadPreferences') and agent.leadPreferences:
                    comp_score += 15.0
            if agent.status == 'pending':
                comp_score = 100.0
            comp_score = min(comp_score, 100.0)

            # 10. Recent Activity / Response Rate (2% weight)
            # Default response time to 2 hours if not set. Match to response rate scale.
            try:
                resp_time = float(perf.response_time) if (perf and perf.response_time is not None) else 2.0
            except (ValueError, TypeError):
                resp_time = 2.0
            resp_rate = max(0.0, min(100.0, 100.0 - (resp_time * 1.5)))

            # Sum of weighted scores
            total_score = (
                (0.25 * req_match) +
                (0.20 * dist_score) +
                (0.15 * exp_score) +
                (0.10 * rating_score) +
                (0.10 * rev_score) +
                (0.05 * clients_score) +
                (0.05 * claims_score) +
                (0.05 * license_score) +
                (0.03 * comp_score) +
                (0.02 * resp_rate)
            )
            return round(total_score, 2)
        except Exception as e:
            logger.error(f"Error calculating weighted score for agent {agent.id if agent else 'None'}: {e}")
            return 0.0

    @staticmethod
    def generate_ai_explanation(agent, distance):
        """
        Dynamically generates a natural language explanation describing why the agent was recommended,
        based on their highest-performing normalized parameters.
        """
        reasons = []

        # 1. Match score
        match_pct = agent.calculated_match_percent
        if match_pct >= 90:
            reasons.append("a profile that closely matches your insurance requirements")

        # 2. Distance
        if distance is not None and distance <= 5:
            reasons.append("exceptional proximity to your location")
        elif distance is not None and distance <= 15:
            reasons.append("close proximity")

        # 3. Experience
        if agent.experience_years >= 10:
            reasons.append("rich professional experience")
        elif agent.experience_years >= 5:
            reasons.append("strong experience")

        # 4. Ratings / Reviews
        if agent.average_rating >= 4.5:
            if agent.review_count >= 15:
                reasons.append("outstanding customer ratings and review count")
            else:
                reasons.append("highly rated customer satisfaction")
        elif agent.review_count >= 20:
            reasons.append("strong track record of customer feedback")

        # 5. Happy clients
        try:
            clients = int(agent.client_base or 0)
        except (ValueError, TypeError):
            clients = 0
        if clients >= 200:
            reasons.append("a large active client base")

        # 6. Claims processed / settled
        perf = getattr(agent, 'performanceStats', None)
        try:
            claims_settled = int(perf.claims_settled) if (perf and perf.claims_settled is not None) else 0
        except (ValueError, TypeError):
            claims_settled = 0
        if claims_settled >= 15:
            reasons.append("a high claim settlement record")

        # 7. Licenses
        profile = getattr(agent, 'profile', None)
        has_irdai = bool(profile.license_number) if profile else False
        has_amfi = bool(profile.arn_number) if profile else False
        if has_irdai and has_amfi:
            reasons.append("fully verified professional licenses (IRDAI and AMFI)")
        elif has_irdai:
            reasons.append("verified IRDAI license")
        elif has_amfi:
            reasons.append("verified AMFI credentials")

        # 8. Response time
        try:
            resp_time = float(perf.response_time) if (perf and perf.response_time is not None) else 2.0
        except (ValueError, TypeError):
            resp_time = 2.0
        if resp_time <= 2:
            reasons.append("an exceptional response rate")

        if not reasons:
            return "This advisor is recommended because of their strong overall performance profile, experience, and dedication to client service."

        # Grammatically connect sentences
        if len(reasons) == 1:
            reasons_str = reasons[0]
        elif len(reasons) == 2:
            reasons_str = f"{reasons[0]} and {reasons[1]}"
        else:
            reasons_str = ", ".join(reasons[:-1]) + f", and {reasons[-1]}"

        return f"This advisor is recommended because they have an excellent balance of {reasons_str}."
