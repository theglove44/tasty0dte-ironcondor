
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
from tastytrade.instruments import Option, OptionType
from tastytrade.dxfeed import Greeks
import strategy

class TestIronFlyLegs(unittest.IsolatedAsyncioTestCase):
    async def test_find_iron_fly_legs(self):
        # Mock Session
        session = MagicMock()
        
        # Mock Options
        # Create a chain of options around ATM (say 5000)
        # Strikes: 4980, 4990, 5000, 5010, 5020
        # Deltas:  Call Deltas decrease as strike increases (ITM -> OTM)
        #          Put Deltas increase (in absolute value) as strike decreases (OTM -> ITM)
        # Actually:
        # Call Delta: 5000 is ~0.50. 4990 is higher (~0.55). 5010 is lower (~0.45).
        
        options = []
        strikes = [4980, 4990, 5000, 5010, 5020]
        
        # Helper to create option
        def make_opt(strike, otype, sym):
            o = MagicMock(spec=Option)
            o.strike_price = strike
            o.option_type = otype
            o.streamer_symbol = sym
            return o

        for k in strikes:
            options.append(make_opt(k, OptionType.CALL, f"C{k}"))
            options.append(make_opt(k, OptionType.PUT, f"P{k}"))
            
        # Mock Greeks
        # We need a way to mock get_greeks_for_chain from strategy.py
        # or we can mock the values it returns if we mock the function itself.
        # But we are testing find_iron_fly_legs which calls get_greeks_for_chain.
        # Ideally we mock get_greeks_for_chain to avoid streamer complexity.
        
        # Mock Greeks
        greeks_map = {}
        
        # Populate Greeks for all options
        # We don't care about precise delta for wings, just that they exist in the map
        for k in strikes:
            delta_c = 0.50 # default
            delta_p = -0.50 # default
            
            # Make ATM distinct if needed, but for availability check just needs to be there.
            if k == 5000:
                delta_c = 0.50
                delta_p = -0.50
            elif k > 5000:
                delta_c = 0.40
                delta_p = -0.60
            elif k < 5000:
                delta_c = 0.60
                delta_p = -0.40
                
            greeks_map[f"C{k}"] = MagicMock(spec=Greeks, delta=delta_c)
            greeks_map[f"P{k}"] = MagicMock(spec=Greeks, delta=delta_p)
        
        # Monkey patch get_greeks_for_chain
        original_get_greeks = strategy.get_greeks_for_chain
        strategy.get_greeks_for_chain = AsyncMock(return_value=greeks_map)
        
        # Mock get_quote_snapshot to return prices
        async def mock_quotes(sess, syms):
            q = {}
            for s in syms:
                qm = MagicMock()
                qm.bid_price = 1.0
                qm.ask_price = 2.0
                q[s] = qm
            return q
            
        strategy.get_quote_snapshot = AsyncMock(side_effect=mock_quotes)
        
        try:
            # Test Logic
            # Target Delta 0.50 (ATM)
            # Wing Width 10
            # Should pick Short Call 5000, Short Put 5000
            # Long Call 5010 (5000 + 10)
            # Long Put 4990 (5000 - 10)
            
            legs = await strategy.find_iron_fly_legs(session, options, target_delta=0.50, wing_width=10)
            
            self.assertIsNotNone(legs)
            self.assertEqual(legs['short_call']['strike'], 5000)
            self.assertEqual(legs['short_put']['strike'], 5000)
            self.assertEqual(legs['long_call']['strike'], 5010)
            self.assertEqual(legs['long_put']['strike'], 4990)
            
            print("Iron Fly Legs Selection Verified!")
            
        finally:
            # Restore
            strategy.get_greeks_for_chain = original_get_greeks

if __name__ == "__main__":
    unittest.main()
