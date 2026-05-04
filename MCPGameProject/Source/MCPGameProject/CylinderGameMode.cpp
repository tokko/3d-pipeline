#include "CylinderGameMode.h"
#include "CylinderCharacter.h"

ACylinderGameMode::ACylinderGameMode()
{
	DefaultPawnClass = ACylinderCharacter::StaticClass();
}
