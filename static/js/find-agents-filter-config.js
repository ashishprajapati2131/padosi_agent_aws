/**
 * Find Agents filter — external types, categories, subtype → backend product tiles.
 */
(function (global) {
  var CAT = {
    HEALTH: { category: 'Health Insurance', label: 'HEALTH' },
    LIFE: { category: 'Life Insurance', label: 'LIFE', sectionId: 'life-insurance-section' },
    MOTOR: { category: 'Motor Insurance', label: 'MOTOR' },
    SME: { category: 'SME Insurance', label: 'SME' }
  };

  function P(label, product) {
    return { label: label, product: product || label };
  }

  var HEALTH_STD = [
    P('Mediclaim', 'Mediclaim'),
    P('Family Mediclaim', 'Family Mediclaim'),
    P('Accident Insurance', 'Personal Accident'),
    P('Critical Illness', 'Critical Illness'),
    P('Top-up', 'Top-up'),
    P('Hospital Cash', 'Hospital Cash'),
    P('Others', 'Others')
  ];

  var LIFE_STD = [
    P('Term / Protection', 'Term Plan'),
    P('Pension Plan', 'Pension Plan'),
    P('Guaranteed Return', 'Saving Plan'),
    P('ULIP Plan', 'ULIP Plan'),
    P('Saving Plan', 'Saving Plan'),
    P('Others', 'Others')
  ];

  var MOTOR_STD = [
    P('Car Insurance', 'Private Car'),
    P('2 Wheeler', 'Two Wheeler'),
    P('Third-party', 'Others'),
    P('Auto Rickshaw', 'Others'),
    P('Commercial Vehicle', 'Commercial Vehicle'),
    P('Others', 'Others')
  ];

  var SME_STD = [
    P('Factory', 'Others'),
    P('Fire', 'Fire'),
    P('Office', 'Others'),
    P('Shop', 'Others'),
    P('Cyber', 'Cyber'),
    P('Transport', 'Others'),
    P('Group Health', 'GPA/GMC'),
    P('Group Term', 'Others'),
    P('Liability', 'Liability'),
    P('Worker', 'Others'),
    P('Property', 'Fire'),
    P('Project', 'Others'),
    P('Others', 'Others')
  ];

  global.PA_FILTER_CONFIG = {
    categories: CAT,
    externals: [
      {
        id: 'buy-new',
        title: 'Buy New Insurance',
        subtitle: '',
        pillValue: 'Buying new insurance',
        icon: 'fa-shopping-cart',
        groups: [
          { key: 'HEALTH', items: HEALTH_STD },
          { key: 'LIFE', items: LIFE_STD },
          { key: 'MOTOR', items: MOTOR_STD },
          { key: 'SME', items: SME_STD }
        ]
      },
      {
        id: 'renew-transfer',
        title: 'Renew or Transfer Policy',
        subtitle: 'Renew or move to a better agent',
        pillValue: 'Port / transfer',
        icon: 'fa-sync-alt',
        hideLife: true,
        groups: [
          { key: 'HEALTH', items: HEALTH_STD },
          { key: 'MOTOR', items: MOTOR_STD },
          { key: 'SME', items: SME_STD }
        ]
      },
      {
        id: 'claim',
        title: 'Claim My Money',
        subtitle: 'Help getting a claim paid',
        pillValue: 'Claim',
        icon: 'fa-file-invoice-dollar',
        footnote: 'Next step will ask your insurer & complaint.',
        groups: [
          { key: 'HEALTH', items: HEALTH_STD },
          { key: 'LIFE', items: LIFE_STD },
          { key: 'MOTOR', items: MOTOR_STD },
          { key: 'SME', items: SME_STD }
        ]
      },
      {
        id: 'check-policy',
        title: 'Check My Policy',
        subtitle: 'Review my existing policy',
        pillValue: 'Insurance audit',
        icon: 'fa-search-dollar',
        groups: [
          { key: 'HEALTH', items: HEALTH_STD },
          { key: 'LIFE', items: LIFE_STD },
          { key: 'MOTOR', items: MOTOR_STD },
          { key: 'SME', items: SME_STD }
        ]
      },
      {
        id: 'other-services',
        title: 'Other Insurance Services',
        subtitle: 'Endorsements, revival, surrender & more',
        pillValue: 'Policy Review',
        icon: 'fa-file-signature',
        groups: [
          {
            key: 'LIFE',
            items: [
              P('Policy Revival', 'Policy Revival'),
              P('Surrender Value', 'Surrender Value'),
              P('Loan Against Insurance', 'Loan Against Insurance'),
              P('Endorsement', 'Endorsement')
            ]
          },
          { key: 'HEALTH', items: [P('Endorsement', 'Endorsement')] },
          { key: 'MOTOR', items: [P('Endorsement', 'Endorsement')] },
          { key: 'SME', items: [P('Endorsement', 'Endorsement')] }
        ]
      },
      {
        id: 'grow-money',
        title: 'Grow My Money',
        subtitle: 'Invest in mutual funds / SIP',
        pillValue: 'Policy Review',
        icon: 'fa-chart-line',
        groups: [
          {
            key: 'LIFE',
            items: [
              P('SIP / STP / SWP', 'SIP / STP / SWP'),
              P('Lumpsum', 'Lumpsum'),
              P('Tax Saving (ELSS)', 'Tax Saving (ELSS)')
            ]
          }
        ]
      }
    ]
  };
})(typeof window !== 'undefined' ? window : this);
