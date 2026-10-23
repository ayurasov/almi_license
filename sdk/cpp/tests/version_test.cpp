#include <gtest/gtest.h>

#include "trust_roots.h"
#include "version.h"

TEST(Version, MatchesCMakeProjectVersion) { EXPECT_EQ(lm::Version(), LM_EXPECTED_VERSION); }

TEST(TrustRoots, MatchesBuildOption) { EXPECT_EQ(lm::TrustRootsName(), LM_EXPECTED_TRUST_ROOTS); }
