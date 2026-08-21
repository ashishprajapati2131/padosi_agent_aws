(function (global) {
  function roundInr(value) {
    if (!isFinite(value)) return 0;
    return Math.round(value);
  }

  function monthlyRate(annualRate) {
    return Number(annualRate) / 100 / 12;
  }

  function parseDate(value) {
    var text = String(value || '').slice(0, 10);
    if (!text) {
      var now = new Date();
      return new Date(now.getFullYear(), now.getMonth(), now.getDate());
    }
    var parts = text.split('-');
    if (parts.length !== 3) {
      var fallback = new Date();
      return new Date(fallback.getFullYear(), fallback.getMonth(), fallback.getDate());
    }
    return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  }

  function fmtDate(d) {
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    return y + '-' + m + '-' + day;
  }

  function addDays(d, days) {
    var copy = new Date(d.getTime());
    copy.setDate(copy.getDate() + days);
    return copy;
  }

  function sip(inputs) {
    var p = Number(inputs.monthly_amount);
    var n = Math.round(Number(inputs.years) * 12);
    var r = monthlyRate(inputs.annual_rate);
    var invested = p * n;
    var fv = n <= 0 ? 0 : Math.abs(r) < 1e-12 ? invested : p * (((Math.pow(1 + r, n) - 1) / r) * (1 + r));
    fv = Math.max(fv, 0);
    return { future_value: roundInr(fv), invested: roundInr(invested), gain: roundInr(Math.max(fv - invested, 0)), primary: roundInr(fv) };
  }

  function goalSip(inputs) {
    var fv = Number(inputs.target_amount);
    var n = Math.round(Number(inputs.years) * 12);
    var r = monthlyRate(inputs.annual_rate);
    var p;
    if (n <= 0) p = fv;
    else if (Math.abs(r) < 1e-12) p = fv / n;
    else p = fv * r / ((Math.pow(1 + r, n) - 1) * (1 + r));
    p = Math.max(p, 0);
    var invested = p * n;
    return { monthly_sip: roundInr(p), target_amount: roundInr(fv), invested: roundInr(invested), gain: roundInr(Math.max(fv - invested, 0)), primary: roundInr(p) };
  }

  function stepUpSip(inputs) {
    var monthly = Number(inputs.monthly_amount);
    var years = Math.round(Number(inputs.years));
    var r = monthlyRate(inputs.annual_rate);
    var step = Number(inputs.step_up_percent) / 100;
    var fv = 0;
    var invested = 0;
    for (var y = 0; y < years; y++) {
      for (var m = 0; m < 12; m++) {
        invested += monthly;
        fv = (fv + monthly) * (1 + r);
      }
      monthly *= (1 + step);
    }
    fv = Math.max(fv, 0);
    return { future_value: roundInr(fv), invested: roundInr(invested), gain: roundInr(Math.max(fv - invested, 0)), primary: roundInr(fv) };
  }

  function lumpsum(inputs) {
    var p = Number(inputs.amount);
    var n = Math.round(Number(inputs.years) * 12);
    var r = monthlyRate(inputs.annual_rate);
    var fv = n > 0 ? p * Math.pow(1 + r, n) : p;
    fv = Math.max(fv, 0);
    return { future_value: roundInr(fv), invested: roundInr(p), gain: roundInr(Math.max(fv - p, 0)), primary: roundInr(fv) };
  }

  function emi(inputs) {
    var p = Number(inputs.loan_amount);
    var n = Math.round(Number(inputs.years) * 12);
    var r = monthlyRate(inputs.annual_rate);
    var instalment;
    if (n <= 0) instalment = p;
    else if (Math.abs(r) < 1e-12) instalment = p / n;
    else instalment = p * r * Math.pow(1 + r, n) / (Math.pow(1 + r, n) - 1);
    var totalPayment = instalment * n;
    return {
      emi: roundInr(instalment),
      principal: roundInr(p),
      total_payment: roundInr(totalPayment),
      total_interest: roundInr(Math.max(totalPayment - p, 0)),
      primary: roundInr(instalment)
    };
  }

  function compoundInterest(inputs) {
    var p = Number(inputs.principal != null ? inputs.principal : inputs.amount);
    var t = Number(inputs.years);
    var rate = Number(inputs.annual_rate) / 100;
    var n = Math.max(Math.round(Number(inputs.frequency || 4)), 1);
    var fv = t > 0 ? p * Math.pow(1 + rate / n, n * t) : p;
    fv = Math.max(fv, 0);
    return { future_value: roundInr(fv), invested: roundInr(p), gain: roundInr(Math.max(fv - p, 0)), primary: roundInr(fv) };
  }

  function inflation(inputs) {
    var p = Number(inputs.current_amount);
    var t = Number(inputs.years);
    var i = Number(inputs.inflation_rate) / 100;
    var future = t > 0 ? p * Math.pow(1 + i, t) : p;
    return {
      future_cost: roundInr(future),
      current_amount: roundInr(p),
      extra_needed: roundInr(Math.max(future - p, 0)),
      primary: roundInr(future)
    };
  }

  function ppf(inputs) {
    var p = Number(inputs.annual_amount);
    var n = Math.round(Number(inputs.years));
    var r = Number(inputs.annual_rate) / 100;
    var invested = p * n;
    var fv = n <= 0 ? 0 : Math.abs(r) < 1e-12 ? invested : p * ((Math.pow(1 + r, n) - 1) / r);
    fv = Math.max(fv, 0);
    return { future_value: roundInr(fv), invested: roundInr(invested), gain: roundInr(Math.max(fv - invested, 0)), primary: roundInr(fv) };
  }

  function humanLifeValue(inputs) {
    var cover = Number(inputs.annual_income) * Number(inputs.years_to_retire) - Number(inputs.existing_savings || 0);
    cover = Math.max(cover, 0);
    return {
      cover_needed: roundInr(cover),
      income_stream: roundInr(Number(inputs.annual_income) * Number(inputs.years_to_retire)),
      existing_savings: roundInr(Number(inputs.existing_savings || 0)),
      primary: roundInr(cover)
    };
  }

  function insurancePremium(inputs) {
    var calcType = String(inputs.calc_type || 'health');
    var baseRate = 0.01;
    if (calcType === 'life') baseRate = 0.005;
    else if (calcType === 'general') baseRate = 0.003;
    var ageFactor = 1 + (Number(inputs.age) - 20) * 0.03;
    var smokingM = String(inputs.smoking) === 'yes' ? 1.4 : 1;
    var genderM = String(inputs.gender) === 'female' ? 0.95 : 1;
    var typeM = calcType === 'health' ? 1.2 : 1;
    var annual = Number(inputs.coverage) * baseRate * ageFactor * smokingM * genderM * typeM;
    annual = Math.max(annual * (1 - Number(inputs.term || 1) / 100), 0);
    return {
      yearly_premium: roundInr(annual),
      monthly_premium: roundInr(annual / 12),
      coverage: roundInr(Number(inputs.coverage)),
      primary: roundInr(annual / 12)
    };
  }

  function healthInsurance(inputs) {
    var base = insurancePremium(Object.assign({}, inputs, { calc_type: 'health' }));
    var extra = Math.max(Number(inputs.members || 1) - 1, 0);
    var yearly = base.yearly_premium * (1 + 0.35 * extra);
    return {
      yearly_premium: roundInr(yearly),
      monthly_premium: roundInr(yearly / 12),
      coverage: roundInr(Number(inputs.coverage)),
      primary: roundInr(yearly / 12)
    };
  }

  function termInsurance(inputs) {
    var result = insurancePremium(Object.assign({}, inputs, { calc_type: 'life' }));
    var yearly = result.yearly_premium * 0.85;
    return {
      yearly_premium: roundInr(yearly),
      monthly_premium: roundInr(yearly / 12),
      coverage: roundInr(Number(inputs.coverage)),
      primary: roundInr(yearly / 12)
    };
  }

  function licCalculator(inputs) {
    var sa = Number(inputs.coverage);
    var years = Math.max(Number(inputs.term), 1);
    var age = Math.max(Number(inputs.age), 18);
    var yearly = (sa / 1000) * (18 + age / 8);
    var bonus = sa * 0.045 * years;
    return {
      yearly_premium: roundInr(yearly),
      monthly_premium: roundInr(yearly / 12),
      maturity: roundInr(sa + bonus),
      bonus: roundInr(bonus),
      coverage: roundInr(sa),
      primary: roundInr(yearly)
    };
  }

  function ulipCalculator(inputs) {
    var net = Math.max(Number(inputs.annual_rate) - Number(inputs.charge_percent || 2.25), 0);
    var result = sip({ monthly_amount: inputs.monthly_amount, years: inputs.years, annual_rate: net });
    var gross = sip({ monthly_amount: inputs.monthly_amount, years: inputs.years, annual_rate: inputs.annual_rate });
    return {
      future_value: result.future_value,
      invested: result.invested,
      gain: result.gain,
      charge_drag: Math.max(gross.future_value - result.future_value, 0),
      primary: result.future_value
    };
  }

  function motorPremium(idv, vehicleAge, ncbPercent, odRate, tp) {
    var age = Math.max(Number(vehicleAge), 0);
    var ncb = Math.min(Math.max(Number(ncbPercent), 0), 50) / 100;
    var od = Math.max(Number(idv) * (odRate + age * 0.002) * (1 - ncb), 0);
    return {
      od_premium: roundInr(od),
      tp_premium: roundInr(tp),
      yearly_premium: roundInr(od + tp),
      idv: roundInr(Number(idv)),
      primary: roundInr(od + tp)
    };
  }

  function bmrCalc(inputs) {
    var bmr = String(inputs.gender) === 'female'
      ? 10 * Number(inputs.weight_kg) + 6.25 * Number(inputs.height_cm) - 5 * Number(inputs.age) - 161
      : 10 * Number(inputs.weight_kg) + 6.25 * Number(inputs.height_cm) - 5 * Number(inputs.age) + 5;
    bmr = Math.max(bmr, 0);
    return { bmr: roundInr(bmr), primary: roundInr(bmr) };
  }

  var engines = {
    'sip-calculator': sip,
    'goal-sip-calculator': goalSip,
    'step-up-sip-calculator': stepUpSip,
    'lumpsum-calculator': lumpsum,
    'investment-calculator': lumpsum,
    'emi-calculator': emi,
    'home-loan-emi-calculator': emi,
    'car-loan-emi-calculator': emi,
    'personal-loan-emi-calculator': emi,
    'compound-interest-calculator': compoundInterest,
    'inflation-calculator': inflation,
    'fd-calculator': compoundInterest,
    'ppf-calculator': ppf,
    'ssy-calculator': function (inputs) {
      var years = Math.min(Math.max(Math.round(Number(inputs.years)), 1), 21);
      return ppf({ annual_amount: Math.min(Number(inputs.annual_amount), 150000), years: years, annual_rate: inputs.annual_rate });
    },
    'savings-calculator': compoundInterest,
    'human-life-value-calculator': humanLifeValue,
    'health-insurance-calculator': healthInsurance,
    'life-insurance-calculator': function (inputs) {
      return insurancePremium(Object.assign({}, inputs, { calc_type: 'life' }));
    },
    'term-insurance-calculator': termInsurance,
    'lic-calculator': licCalculator,
    'ulip-calculator': ulipCalculator,
    'home-loan-insurance-calculator': function (inputs) {
      var cover = Math.max(Number(inputs.loan_amount), 0);
      var yearly = cover * 0.0035 * (1 + Number(inputs.years) / 40);
      return {
        cover_needed: roundInr(cover),
        yearly_premium: roundInr(yearly),
        monthly_premium: roundInr(yearly / 12),
        outstanding: roundInr(cover),
        primary: roundInr(cover)
      };
    },
    'car-insurance-calculator': function (inputs) {
      return motorPremium(inputs.idv, inputs.vehicle_age, inputs.ncb_percent, 0.025, 2094);
    },
    'bike-insurance-calculator': function (inputs) {
      return motorPremium(inputs.idv, inputs.vehicle_age, inputs.ncb_percent, 0.035, 714);
    },
    'idv-calculator': function (inputs) {
      var price = Number(inputs.ex_showroom);
      var age = Math.max(Number(inputs.vehicle_age), 0);
      var dep;
      if (age <= 0.5) dep = 0.05;
      else if (age <= 1) dep = 0.15;
      else if (age <= 2) dep = 0.20;
      else if (age <= 3) dep = 0.30;
      else if (age <= 4) dep = 0.40;
      else if (age <= 5) dep = 0.50;
      else dep = Math.min(0.50 + 0.05 * (age - 5), 0.80);
      var idv = price * (1 - dep);
      return { idv: roundInr(idv), depreciation: roundInr(price - idv), ex_showroom: roundInr(price), primary: roundInr(idv) };
    },
    'travel-insurance-calculator': function (inputs) {
      var destM = { domestic: 0.6, asia: 1, worldwide: 1.6 }[String(inputs.destination_type)] || 1;
      var days = Math.max(Number(inputs.trip_days), 1);
      var people = Math.max(Number(inputs.travellers), 1);
      var premium = days * people * destM * (Number(inputs.coverage) / 100000) * 45;
      return {
        yearly_premium: roundInr(premium),
        per_person: roundInr(premium / people),
        coverage: roundInr(Number(inputs.coverage)),
        primary: roundInr(premium)
      };
    },
    'swp-calculator': function (inputs) {
      var balance = Number(inputs.amount);
      var w = Number(inputs.monthly_withdrawal);
      var n = Math.round(Number(inputs.years) * 12);
      var r = monthlyRate(inputs.annual_rate);
      var withdrawn = 0;
      for (var i = 0; i < n; i++) {
        balance = balance * (1 + r) - w;
        if (balance < 0) {
          withdrawn += w + balance;
          balance = 0;
          break;
        }
        withdrawn += w;
      }
      return {
        remaining: roundInr(Math.max(balance, 0)),
        total_withdrawn: roundInr(Math.max(withdrawn, 0)),
        invested: roundInr(Number(inputs.amount)),
        primary: roundInr(Math.max(balance, 0))
      };
    },
    'nps-calculator': function (inputs) {
      var result = sip(inputs);
      var corpus = result.future_value;
      return {
        future_value: corpus,
        invested: result.invested,
        gain: result.gain,
        lump_sum: roundInr(corpus * 0.6),
        annuity_corpus: roundInr(corpus * 0.4),
        yearly_pension: roundInr(corpus * 0.4 * 0.06),
        primary: corpus
      };
    },
    'retirement-calculator': function (inputs) {
      var futureExpense = Number(inputs.monthly_expense) * Math.pow(1 + Number(inputs.inflation_rate) / 100, Number(inputs.years_to_retire));
      var n = Math.round(Number(inputs.retirement_years) * 12);
      var r = monthlyRate(inputs.annual_rate);
      var corpus;
      if (n <= 0) corpus = 0;
      else if (Math.abs(r) < 1e-12) corpus = futureExpense * n;
      else corpus = futureExpense * (1 - Math.pow(1 + r, -n)) / r;
      var sipNeeded = goalSip({ target_amount: corpus, years: inputs.years_to_retire, annual_rate: inputs.annual_rate });
      return {
        corpus_needed: roundInr(corpus),
        future_expense: roundInr(futureExpense),
        monthly_sip: sipNeeded.monthly_sip,
        primary: roundInr(corpus)
      };
    },
    'pension-calculator': function (inputs) {
      var pmt = Number(inputs.monthly_pension);
      var r = monthlyRate(inputs.annual_rate);
      var nPayout = 20 * 12;
      var corpus = Math.abs(r) < 1e-12 ? pmt * nPayout : pmt * (1 - Math.pow(1 + r, -nPayout)) / r;
      var needed = goalSip({ target_amount: corpus, years: inputs.years, annual_rate: inputs.annual_rate });
      return {
        monthly_sip: needed.monthly_sip,
        corpus_needed: roundInr(corpus),
        invested: needed.invested,
        gain: needed.gain,
        primary: needed.monthly_sip
      };
    },
    'epf-calculator': sip,
    'rd-calculator': function (inputs) {
      var p = Number(inputs.monthly_amount);
      var n = Math.round(Number(inputs.years) * 12);
      var r = monthlyRate(inputs.annual_rate);
      var invested = p * n;
      var fv = n <= 0 ? 0 : Math.abs(r) < 1e-12 ? invested : p * ((Math.pow(1 + r, n) - 1) / r);
      fv = Math.max(fv, 0);
      return { future_value: roundInr(fv), invested: roundInr(invested), gain: roundInr(Math.max(fv - invested, 0)), primary: roundInr(fv) };
    },
    'elss-calculator': sip,
    'gratuity-calculator': function (inputs) {
      var years = Math.max(Math.floor(Number(inputs.years)), 0);
      var uncapped = (15 / 26) * Number(inputs.monthly_salary) * years;
      var cap = 2000000;
      var amount = Math.min(Math.max(uncapped, 0), cap);
      return { gratuity: roundInr(amount), uncapped: roundInr(Math.max(uncapped, 0)), statutory_cap: roundInr(cap), primary: roundInr(amount) };
    },
    'cost-of-delay-calculator': function (inputs) {
      var delay = Math.min(Number(inputs.delay_years), Number(inputs.years));
      var startNow = sip({ monthly_amount: inputs.monthly_amount, years: inputs.years, annual_rate: inputs.annual_rate });
      var delayed = sip({ monthly_amount: inputs.monthly_amount, years: Math.max(Number(inputs.years) - delay, 0), annual_rate: inputs.annual_rate });
      var cost = Math.max(startNow.future_value - delayed.future_value, 0);
      return { cost: cost, start_now: startNow.future_value, delayed_value: delayed.future_value, primary: cost };
    },
    'power-of-compounding-calculator': sip,
    'future-value-calculator': lumpsum,
    'increasing-contribution-calculator': stepUpSip,
    'bond-yield-calculator': function (inputs) {
      var face = Number(inputs.face_value);
      var px = Math.max(Number(inputs.price), 0.01);
      var couponIncome = face * Number(inputs.coupon) / 100;
      var current = couponIncome / px * 100;
      return { current_yield: Math.round(current * 100) / 100, coupon_income: roundInr(couponIncome), price: roundInr(px), primary: Math.round(current * 100) / 100 };
    },
    'annuity-payout-calculator': function (inputs) {
      var p = Number(inputs.amount);
      var n = Math.round(Number(inputs.years) * 12);
      var r = monthlyRate(inputs.annual_rate);
      var pmt;
      if (n <= 0) pmt = p;
      else if (Math.abs(r) < 1e-12) pmt = p / n;
      else pmt = p * r / (1 - Math.pow(1 + r, -n));
      return {
        monthly_payout: roundInr(pmt),
        yearly_payout: roundInr(pmt * 12),
        total_payout: roundInr(pmt * n),
        invested: roundInr(p),
        primary: roundInr(pmt)
      };
    },
    'net-worth-calculator': function (inputs) {
      var a = Number(inputs.assets);
      var l = Number(inputs.liabilities);
      return { net_worth: roundInr(a - l), assets: roundInr(a), liabilities: roundInr(l), primary: roundInr(a - l) };
    },
    'asset-allocation-calculator': function (inputs) {
      var equityPct = Math.min(Math.max(100 - Number(inputs.age), 20), 80);
      var otherPct = 10;
      var debtPct = Math.max(100 - equityPct - otherPct, 0);
      var total = Number(inputs.amount);
      return {
        equity: roundInr(total * equityPct / 100),
        debt: roundInr(total * debtPct / 100),
        other: roundInr(total * otherPct / 100),
        primary: roundInr(total * equityPct / 100)
      };
    },
    'present-value-calculator': function (inputs) {
      var fv = Number(inputs.future_amount);
      var t = Number(inputs.years);
      var rate = Number(inputs.annual_rate) / 100;
      var pv = t > 0 ? fv / Math.pow(1 + rate, t) : fv;
      return { present_value: roundInr(pv), future_amount: roundInr(fv), discount: roundInr(Math.max(fv - pv, 0)), primary: roundInr(pv) };
    },
    'income-tax-calculator': function (inputs) {
      var income = Math.max(Number(inputs.annual_income), 0);
      var slabs = [[400000, 0], [800000, 0.05], [1200000, 0.10], [1600000, 0.15], [2000000, 0.20], [2400000, 0.25], [Infinity, 0.30]];
      var tax = 0;
      var lower = 0;
      for (var i = 0; i < slabs.length; i++) {
        var upper = slabs[i][0];
        var rate = slabs[i][1];
        var band = Math.min(income, upper) - lower;
        if (band > 0) tax += band * rate;
        if (income <= upper) break;
        lower = upper;
      }
      if (income <= 1200000) tax = Math.max(tax - 60000, 0);
      var cess = tax * 0.04;
      var total = tax + cess;
      return { tax_before_cess: roundInr(tax), cess: roundInr(cess), total_tax: roundInr(total), take_home: roundInr(income - total), primary: roundInr(total) };
    },
    'hra-calculator': function (inputs) {
      var basic = Number(inputs.basic);
      var received = Number(inputs.hra_received);
      var rent = Number(inputs.rent_paid);
      var pct = String(inputs.city_type) === 'non_metro' ? 0.4 : 0.5;
      var exemption = Math.min(received, Math.max(rent - 0.1 * basic, 0), pct * basic);
      exemption = Math.max(exemption, 0);
      return { exemption: roundInr(exemption), taxable_hra: roundInr(Math.max(received - exemption, 0)), hra_received: roundInr(received), primary: roundInr(exemption) };
    },
    'gst-calculator': function (inputs) {
      var amt = Number(inputs.amount);
      var rate = Number(inputs.gst_rate) / 100;
      var base, gstAmt, total;
      if (String(inputs.mode) === 'inclusive') {
        total = amt;
        base = rate > -0.999 ? amt / (1 + rate) : amt;
        gstAmt = total - base;
      } else {
        base = amt;
        gstAmt = amt * rate;
        total = base + gstAmt;
      }
      return { gst_amount: roundInr(gstAmt), base_amount: roundInr(base), total: roundInr(total), primary: roundInr(gstAmt) };
    },
    'section-80d-calculator': function (inputs) {
      var selfCap = String(inputs.self_senior) === 'yes' ? 50000 : 25000;
      var parentCap = String(inputs.parents_senior) === 'yes' ? 50000 : 25000;
      var prev = Math.min(Math.max(Number(inputs.preventive || 0), 0), 5000);
      var selfDed = Math.min(Math.max(Number(inputs.self_premium), 0) + prev, selfCap);
      var parentDed = Math.min(Math.max(Number(inputs.parents_premium), 0), parentCap);
      return {
        total_deduction: roundInr(selfDed + parentDed),
        self_deduction: roundInr(selfDed),
        parents_deduction: roundInr(parentDed),
        primary: roundInr(selfDed + parentDed)
      };
    },
    'ulip-vs-mutual-fund-calculator': function (inputs) {
      var ulip = ulipCalculator({
        monthly_amount: inputs.monthly_amount,
        years: inputs.years,
        annual_rate: inputs.ulip_rate,
        charge_percent: inputs.charge_percent
      });
      var mf = sip({ monthly_amount: inputs.monthly_amount, years: inputs.years, annual_rate: inputs.mf_rate });
      var termCost = Number(inputs.term_premium) * 12 * Number(inputs.years);
      var termPlus = Math.max(mf.future_value - roundInr(termCost), 0);
      return {
        ulip_value: ulip.future_value,
        mf_value: mf.future_value,
        term_plus_sip: termPlus,
        difference: roundInr(termPlus - ulip.future_value),
        primary: termPlus
      };
    },
    'endowment-vs-mutual-fund-calculator': function (inputs) {
      var endw = sip({ monthly_amount: inputs.monthly_amount, years: inputs.years, annual_rate: inputs.endowment_rate });
      var mf = sip({ monthly_amount: inputs.monthly_amount, years: inputs.years, annual_rate: inputs.mf_rate });
      var termCost = Number(inputs.term_premium) * 12 * Number(inputs.years);
      var termPlus = Math.max(mf.future_value - roundInr(termCost), 0);
      return {
        endowment_value: endw.future_value,
        mf_value: mf.future_value,
        term_plus_sip: termPlus,
        difference: roundInr(termPlus - endw.future_value),
        primary: termPlus
      };
    },
    'family-floater-vs-individual-calculator': function (inputs) {
      var n = Math.max(Number(inputs.members), 1);
      var floater = healthInsurance({ age: inputs.age, coverage: inputs.coverage, members: n, gender: 'male', smoking: 'no', term: 1 });
      var individual = healthInsurance({ age: inputs.age, coverage: inputs.coverage, members: 1, gender: 'male', smoking: 'no', term: 1 });
      var individualTotal = individual.yearly_premium * n;
      return {
        floater_premium: floater.yearly_premium,
        individual_premium: roundInr(individualTotal),
        savings: roundInr(Math.max(individualTotal - floater.yearly_premium, 0)),
        primary: floater.yearly_premium
      };
    },
    'super-top-up-calculator': function (inputs) {
      var ageF = 1 + (Number(inputs.age) - 20) * 0.025;
      var yearly = Number(inputs.extra_cover) * 0.0018 * ageF;
      return {
        yearly_premium: roundInr(yearly),
        total_cover: roundInr(Number(inputs.base_cover) + Number(inputs.extra_cover)),
        deductible: roundInr(Number(inputs.deductible)),
        primary: roundInr(yearly)
      };
    },
    'life-cover-calculator': function (inputs) {
      var need = Number(inputs.annual_income) * Number(inputs.years_to_retire) + Number(inputs.liabilities || 0) - Number(inputs.existing_cover || 0);
      need = Math.max(need, 0);
      return {
        cover_needed: roundInr(need),
        income_stream: roundInr(Number(inputs.annual_income) * Number(inputs.years_to_retire)),
        liabilities: roundInr(Number(inputs.liabilities || 0)),
        existing_cover: roundInr(Number(inputs.existing_cover || 0)),
        primary: roundInr(need)
      };
    },
    'critical-illness-cover-calculator': function (inputs) {
      var ageF = 1 + (Number(inputs.age) - 20) * 0.04;
      var yearly = Number(inputs.coverage) * 0.007 * ageF;
      return {
        yearly_premium: roundInr(yearly),
        monthly_premium: roundInr(yearly / 12),
        coverage: roundInr(Number(inputs.coverage)),
        primary: roundInr(yearly)
      };
    },
    'sip-vs-lumpsum-calculator': function (inputs) {
      var sipR = sip(inputs);
      var lumpAmount = Number(inputs.monthly_amount) * 12 * Number(inputs.years);
      var lump = lumpsum({ amount: lumpAmount, years: inputs.years, annual_rate: inputs.annual_rate });
      return {
        sip_value: sipR.future_value,
        lumpsum_value: lump.future_value,
        sip_invested: sipR.invested,
        lumpsum_invested: lump.invested,
        primary: sipR.future_value
      };
    },
    'bmi-calculator': function (inputs) {
      var h = Math.max(Number(inputs.height_cm), 1) / 100;
      var bmi = Number(inputs.weight_kg) / (h * h);
      var category = bmi < 18.5 ? 'Underweight' : bmi < 25 ? 'Normal' : bmi < 30 ? 'Overweight' : 'Obese';
      return { bmi: Math.round(bmi * 10) / 10, category: category, weight_kg: Math.round(Number(inputs.weight_kg) * 10) / 10, primary: Math.round(bmi * 10) / 10 };
    },
    'ideal-weight-calculator': function (inputs) {
      var inches = Number(inputs.height_cm) / 2.54;
      var over = Math.max(inches - 60, 0);
      var ideal = String(inputs.gender) === 'female' ? 45.5 + 2.3 * over : 50 + 2.3 * over;
      return { ideal_weight: Math.round(ideal * 10) / 10, height_cm: Math.round(Number(inputs.height_cm) * 10) / 10, primary: Math.round(ideal * 10) / 10 };
    },
    'bmr-calculator': bmrCalc,
    'calorie-calculator': function (inputs) {
      var bmr = bmrCalc(inputs).bmr;
      var factors = { sedentary: 1.2, light: 1.375, moderate: 1.55, active: 1.725, very_active: 1.9 };
      var tdee = bmr * (factors[String(inputs.activity)] || 1.55);
      return { calories: roundInr(tdee), bmr: bmr, cut: roundInr(tdee - 500), bulk: roundInr(tdee + 300), primary: roundInr(tdee) };
    },
    'body-fat-calculator': function (inputs) {
      var height = Math.max(Number(inputs.height_cm), 1);
      var waist = Math.max(Number(inputs.waist_cm), 1);
      var neck = Math.max(Number(inputs.neck_cm), 1);
      var hip = Math.max(Number(inputs.hip_cm), 1);
      var value;
      try {
        if (String(inputs.gender) === 'female') {
          value = 495 / (1.29579 - 0.35004 * Math.log10(waist + hip - neck) + 0.221 * Math.log10(height)) - 450;
        } else {
          value = 495 / (1.0324 - 0.19077 * Math.log10(Math.max(waist - neck, 0.1)) + 0.15456 * Math.log10(height)) - 450;
        }
      } catch (e) {
        value = 20;
      }
      value = Math.min(Math.max(value, 1), 70);
      return { body_fat: Math.round(value * 10) / 10, primary: Math.round(value * 10) / 10 };
    },
    'macro-calculator': function (inputs) {
      var kcal = Math.max(Number(inputs.calories), 0);
      var pPct = 0.3, cPct = 0.4, fPct = 0.3;
      if (String(inputs.goal) === 'cut') { pPct = 0.4; cPct = 0.35; fPct = 0.25; }
      else if (String(inputs.goal) === 'bulk') { pPct = 0.3; cPct = 0.45; fPct = 0.25; }
      return {
        protein: roundInr((kcal * pPct) / 4),
        carbs: roundInr((kcal * cPct) / 4),
        fat: roundInr((kcal * fPct) / 9),
        calories: roundInr(kcal),
        primary: roundInr((kcal * pPct) / 4)
      };
    },
    'ovulation-calculator': function (inputs) {
      var start = parseDate(inputs.lmp);
      var cycle = Math.round(Number(inputs.cycle_length || 28));
      var ovulation = addDays(start, cycle - 14);
      return {
        ovulation_date: fmtDate(ovulation),
        fertile_start: fmtDate(addDays(ovulation, -5)),
        fertile_end: fmtDate(ovulation),
        next_period: fmtDate(addDays(start, cycle)),
        primary: fmtDate(ovulation)
      };
    },
    'pregnancy-calculator': function (inputs) {
      var start = parseDate(inputs.lmp);
      var today = parseDate('');
      var days = Math.max(Math.round((today - start) / 86400000), 0);
      var weeks = Math.floor(days / 7);
      var trimester = weeks < 13 ? 1 : weeks < 27 ? 2 : 3;
      return {
        weeks: weeks,
        days: days % 7,
        trimester: trimester,
        due_date: fmtDate(addDays(start, 280)),
        primary: weeks
      };
    },
    'pregnancy-conception-calculator': function (inputs) {
      var start = parseDate(inputs.lmp);
      var cycle = Math.round(Number(inputs.cycle_length || 28));
      var conception = addDays(start, cycle - 14);
      return {
        conception_date: fmtDate(conception),
        due_date: fmtDate(addDays(start, 280)),
        primary: fmtDate(conception)
      };
    },
    'pregnancy-weight-gain-calculator': function (inputs) {
      var h = Math.max(Number(inputs.height_cm), 1) / 100;
      var bmi = Number(inputs.pre_weight) / (h * h);
      var total = bmi < 18.5 ? 14 : bmi < 25 ? 12.5 : bmi < 30 ? 9 : 7;
      var w = Math.min(Math.max(Number(inputs.week), 0), 40);
      var recommended = total * (w / 40);
      return {
        recommended_gain: Math.round(recommended * 10) / 10,
        total_gain: total,
        bmi: Math.round(bmi * 10) / 10,
        primary: Math.round(recommended * 10) / 10
      };
    },
    'due-date-calculator': function (inputs) {
      var start = parseDate(inputs.lmp);
      var due = addDays(start, 280);
      return {
        due_date: fmtDate(due),
        conception_date: fmtDate(addDays(start, 14)),
        primary: fmtDate(due)
      };
    }
  };

  var aliases = {
    sip: 'sip-calculator',
    'goal-sip': 'goal-sip-calculator',
    'step-up-sip': 'step-up-sip-calculator',
    lumpsum: 'lumpsum-calculator',
    emi: 'emi-calculator',
    'compound-interest': 'compound-interest-calculator',
    inflation: 'inflation-calculator',
    fd: 'fd-calculator',
    ppf: 'ppf-calculator',
    'human-life-value': 'human-life-value-calculator',
    'insurance-premium': 'health-insurance-calculator',
    swp: 'swp-calculator',
    nps: 'nps-calculator',
    retirement: 'retirement-calculator',
    pension: 'pension-calculator',
    epf: 'epf-calculator',
    rd: 'rd-calculator',
    gratuity: 'gratuity-calculator',
    'cost-of-delay': 'cost-of-delay-calculator',
    'power-of-compounding': 'power-of-compounding-calculator',
    'future-value': 'future-value-calculator',
    'increasing-contribution': 'increasing-contribution-calculator',
    'bond-yield': 'bond-yield-calculator',
    'annuity-payout': 'annuity-payout-calculator',
    'net-worth': 'net-worth-calculator',
    'asset-allocation': 'asset-allocation-calculator',
    'present-value': 'present-value-calculator',
    'income-tax': 'income-tax-calculator',
    hra: 'hra-calculator',
    gst: 'gst-calculator'
  };
  Object.keys(aliases).forEach(function (oldKey) {
    if (!engines[oldKey] && engines[aliases[oldKey]]) {
      engines[oldKey] = engines[aliases[oldKey]];
    }
  });

  global.PACalcEngines = engines;
})(window);
